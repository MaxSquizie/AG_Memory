from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic

import numpy as np
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from vispy import scene, use
from vispy.scene.visuals import Markers
from vispy.visuals.filters import MarkerPickingFilter

from ah.bootstrap import RuntimeServices
from ah.config import GUISettings
from ah.ignition import TickResult

from .graph_state import (
    GraphVisualMapper,
    VisualEdge,
    VisualGraph,
    build_edge_focus_geometry,
    build_focus_geometry,
    rank_visible_label_indices,
    pick_edge_key_2d,
)


use(app="PySide6")


@dataclass(frozen=True, slots=True)
class _FlowTrack:
    source_uid: str
    target_uid: str
    via_uid: str
    relation: str
    strength: float
    last_event: float
    event_count: int
    started: float


class GraphCanvasWidget(QWidget):
    """GPU 2.5D/3D observer with read-only node and edge interaction state."""

    node_selected = Signal(str)
    node_hovered = Signal(str)
    edge_selected = Signal(str)
    edge_hovered = Signal(str)

    def __init__(self, services: RuntimeServices, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.settings = services.config.gui
        self.mapper = GraphVisualMapper()
        self.visual: VisualGraph | None = None
        self._snapshot = None
        self._flows: dict[str, _FlowTrack] = {}
        self._flow_lock = Lock()
        self._last_uid_order: tuple[str, ...] = ()
        self._selected_uid: str | None = None
        self._selected_edge_key: str | None = None
        self._hover_uid: str | None = None
        self._hover_edge_key: str | None = None
        self._last_hover_pick = 0.0
        self._live_updates_enabled = True

        self.canvas = scene.SceneCanvas(
            keys="interactive",
            bgcolor=(0.035, 0.045, 0.065, 1.0),
            show=False,
            vsync=True,
        )
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = scene.cameras.TurntableCamera(
            fov=42,
            elevation=24,
            azimuth=35,
            distance=35,
        )

        placeholder_segment = np.asarray(
            ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)), dtype=np.float32
        )
        placeholder_point = np.asarray(((0.0, 0.0, 0.0),), dtype=np.float32)

        self.structural_lines = scene.visuals.Line(
            pos=placeholder_segment,
            color=(0.62, 0.64, 0.68, 0.0),
            connect="segments",
            width=1.0,
            method="gl",
            parent=self.view.scene,
        )
        self.structural_lines.visible = False
        self.relation_lines = scene.visuals.Line(
            pos=placeholder_segment.copy(),
            color=(0.30, 0.72, 1.0, 0.0),
            connect="segments",
            width=1.5,
            method="gl",
            parent=self.view.scene,
        )
        self.relation_lines.visible = False

        self.nodes = Markers(parent=self.view.scene)
        self._prime_markers(self.nodes, placeholder_point)
        self.nodes.update_gl_state(depth_test=True, blend=True)
        self.nodes.scaling = False
        self._picker = MarkerPickingFilter()
        self.nodes.attach(self._picker)
        self._picker.enabled = False

        self.flow_lines = scene.visuals.Line(
            pos=placeholder_segment.copy(),
            color=(0.95, 0.03, 0.02, 0.0),
            connect="segments",
            width=self.settings.propagation_edge_width,
            method="gl",
            parent=self.view.scene,
        )
        self.flow_lines.visible = False

        self.pulse_markers = Markers(parent=self.view.scene)
        self._prime_markers(self.pulse_markers, placeholder_point)
        self.pulse_markers.update_gl_state(depth_test=True, blend=True)
        self.pulse_markers.scaling = False

        self.selection_lines = scene.visuals.Line(
            pos=placeholder_segment.copy(),
            color=(0.25, 0.95, 1.0, 0.0),
            connect="segments",
            width=self.settings.focus_line_width,
            method="gl",
            parent=self.view.scene,
        )
        self.selection_lines.visible = False
        self.selection_markers = Markers(parent=self.view.scene)
        self._prime_markers(self.selection_markers, placeholder_point)
        self.selection_markers.update_gl_state(depth_test=True, blend=True)
        self.selection_markers.scaling = False

        self.hover_lines = scene.visuals.Line(
            pos=placeholder_segment.copy(),
            color=(1.0, 0.78, 0.20, 0.0),
            connect="segments",
            width=self.settings.focus_line_width,
            method="gl",
            parent=self.view.scene,
        )
        self.hover_lines.visible = False
        self.hover_markers = Markers(parent=self.view.scene)
        self._prime_markers(self.hover_markers, placeholder_point)
        self.hover_markers.update_gl_state(depth_test=True, blend=True)
        self.hover_markers.scaling = False

        self.labels = scene.visuals.Text(
            text="",
            pos=(0.0, 0.0, 0.0),
            color=(0.92, 0.95, 1.0, 0.92),
            font_size=8,
            anchor_x="left",
            anchor_y="bottom",
            parent=self.view.scene,
        )
        self.labels.visible = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas.native)

        self.canvas.events.mouse_press.connect(self._on_mouse_press)
        self.canvas.events.mouse_move.connect(self._on_mouse_move)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self._restart_timer()
        self.services.clock.add_listener(self._on_tick_from_clock)

    @staticmethod
    def _prime_markers(markers: Markers, placeholder_point: np.ndarray) -> None:
        markers.set_data(
            pos=placeholder_point,
            face_color=(1.0, 1.0, 1.0, 0.0),
            edge_color=(1.0, 1.0, 1.0, 0.0),
            size=1.0,
            edge_width=0.0,
            symbol="disc",
        )
        markers.visible = False

    def closeEvent(self, event) -> None:  # noqa: N802
        self.services.clock.remove_listener(self._on_tick_from_clock)
        super().closeEvent(event)

    def set_settings(self, settings: GUISettings) -> None:
        self.settings = settings
        self.selection_lines.width = settings.focus_line_width
        self.hover_lines.width = settings.focus_line_width
        self.flow_lines.width = settings.propagation_edge_width
        self._restart_timer()
        self.refresh()

    def set_live_updates_enabled(self, enabled: bool) -> None:
        """Pause/resume expensive graph snapshots and VisPy buffer rebuilds.

        Cognitive runtime continues normally. This switch affects visualization only
        and is used by long diagnostic runs where redrawing the same growing graph at
        GUI frequency provides no value and can create substantial allocator/driver
        pressure.
        """
        enabled = bool(enabled)
        if enabled == self._live_updates_enabled:
            return
        self._live_updates_enabled = enabled
        if enabled:
            self._restart_timer()
            self.refresh()
            return

        self.timer.stop()
        with self._flow_lock:
            self._flows.clear()
        self.flow_lines.visible = False
        self.pulse_markers.visible = False
        self.canvas.update()

    def set_selected_uid(self, uid: str | None) -> None:
        self._selected_uid = uid or None
        if self._selected_uid is not None:
            self._selected_edge_key = None
        self._update_focus_layers()
        self.canvas.update()

    def set_selected_edge_key(self, key: str | None) -> None:
        self._selected_edge_key = key or None
        if self._selected_edge_key is not None:
            self._selected_uid = None
        self._update_focus_layers()
        self.canvas.update()

    @property
    def selected_uid(self) -> str | None:
        return self._selected_uid

    @property
    def selected_edge_key(self) -> str | None:
        return self._selected_edge_key

    @property
    def hover_uid(self) -> str | None:
        return self._hover_uid

    @property
    def hover_edge_key(self) -> str | None:
        return self._hover_edge_key

    def edge_descriptor(self, key: str | None) -> VisualEdge | None:
        if not key or self.visual is None:
            return None
        return self.visual.edge_index.get(key)

    def _restart_timer(self) -> None:
        if not self._live_updates_enabled:
            self.timer.stop()
            return
        interval_ms = max(1, round(1000 / max(1, self.settings.refresh_hz)))
        self.timer.start(interval_ms)

    def _on_tick_from_clock(self, result: TickResult) -> None:
        if not self._live_updates_enabled:
            return
        # Tick frequency must not determine animation readability. We aggregate real
        # propagation events into persistent directed tracks and animate those tracks
        # on GUI time. A 20 Hz or 200 Hz engine therefore shows the same direction.
        now = monotonic()
        with self._flow_lock:
            for event in result.propagations:
                key = f"{event.source.uid}|{event.target.uid}|{event.via_uid}|{event.relation}"
                existing = self._flows.get(key)
                if existing is None:
                    self._flows[key] = _FlowTrack(
                        event.source.uid,
                        event.target.uid,
                        event.via_uid,
                        event.relation,
                        max(0.0, event.amount),
                        now,
                        1,
                        now,
                    )
                else:
                    # Smooth bursts without resetting motion back to the source.
                    self._flows[key] = _FlowTrack(
                        existing.source_uid,
                        existing.target_uid,
                        existing.via_uid,
                        existing.relation,
                        max(event.amount, existing.strength * 0.72 + event.amount * 0.28),
                        now,
                        existing.event_count + 1,
                        existing.started,
                    )

    def push_tick(self, result: TickResult) -> None:
        self._on_tick_from_clock(result)
        self.refresh()

    def refresh(self) -> None:
        if not self._live_updates_enabled:
            return
        snapshot = self.services.graph_inspector.snapshot()
        visual = self.mapper.build(
            snapshot,
            self.settings,
            x_max=self.services.config.ignition.x_max,
        )
        self._snapshot = snapshot
        self.visual = visual
        self._last_uid_order = visual.node_uids

        if len(visual.structural_segments):
            self.structural_lines.set_data(
                pos=visual.structural_segments,
                color=visual.structural_colors,
                connect="segments",
            )
            self.structural_lines.visible = True
        else:
            self.structural_lines.visible = False

        if len(visual.relation_segments):
            self.relation_lines.set_data(
                pos=visual.relation_segments,
                color=visual.relation_colors,
                connect="segments",
            )
            self.relation_lines.visible = True
        else:
            self.relation_lines.visible = False

        if len(visual.positions):
            self.nodes.set_data(
                pos=visual.positions,
                face_color=visual.face_colors,
                edge_color=visual.edge_colors,
                size=visual.sizes,
                edge_width=1.35,
                symbol="disc",
            )
            self.nodes.visible = True
        else:
            self.nodes.visible = False

        if self.settings.show_labels and self.settings.max_labels > 0 and len(visual.node_uids):
            ranked = rank_visible_label_indices(snapshot, visual, self.settings.max_labels)
            by_uid = {node.uid: node for node in snapshot.nodes}
            texts = [by_uid[visual.node_uids[i]].semantic[:72] for i in ranked]
            label_pos = visual.positions[list(ranked)].copy()
            if len(label_pos):
                label_pos[:, 0] += 0.22
                label_pos[:, 1] += 0.22
            self.labels.text = texts
            self.labels.pos = label_pos
            self.labels.visible = bool(len(ranked))
        else:
            self.labels.text = ""
            self.labels.visible = False

        if self._selected_uid and self._selected_uid not in visual.node_index:
            self._selected_uid = None
            self.node_selected.emit("")
        if self._hover_uid and self._hover_uid not in visual.node_index:
            self._set_hover_target(None, None)
        if self._selected_edge_key and self._selected_edge_key not in visual.edge_index:
            self._selected_edge_key = None
            self.edge_selected.emit("")
        if self._hover_edge_key and self._hover_edge_key not in visual.edge_index:
            self._set_hover_target(None, None)

        self._update_focus_layers()
        self._update_flows(visual)
        self.canvas.update()

    def _update_flows(self, visual: VisualGraph) -> None:
        now = monotonic()
        index = visual.node_index
        hold = max(0.05, self.settings.propagation_duration_seconds)
        cycles = self.settings.propagation_cycles_per_second
        tail_points = self.settings.propagation_tail_points
        tail_spacing = self.settings.propagation_tail_spacing
        x_max = max(1e-9, self.services.config.ignition.x_max)

        with self._flow_lock:
            tracks = dict(self._flows)

        alive: dict[str, _FlowTrack] = {}
        marker_positions: list[np.ndarray] = []
        marker_colors: list[tuple[float, float, float, float]] = []
        marker_sizes: list[float] = []
        line_segments: list[np.ndarray] = []
        line_colors: list[np.ndarray] = []

        for key, track in tracks.items():
            age = now - track.last_event
            if age >= hold:
                continue
            if track.source_uid not in index or track.target_uid not in index:
                continue
            alive[key] = track
            freshness = max(0.0, 1.0 - age / hold)
            strength = max(0.0, min(1.0, track.strength / x_max))
            a = visual.positions[index[track.source_uid]]
            b = visual.positions[index[track.target_uid]]

            line_segments.extend((a, b))
            line_alpha = 0.16 + 0.70 * freshness * (0.35 + 0.65 * strength)
            c = np.asarray((0.98, 0.025, 0.018, line_alpha), dtype=np.float32)
            line_colors.extend((c, c.copy()))

            # A bright head followed by progressively darker points makes direction
            # readable even when new engine ticks arrive faster than the GUI refresh.
            head_phase = ((now - track.started) * cycles) % 1.0
            for tail_index in range(tail_points):
                t = head_phase - tail_index * tail_spacing
                if t < 0.0:
                    continue
                smooth_t = t * t * (3.0 - 2.0 * t)
                marker_positions.append(a * (1.0 - smooth_t) + b * smooth_t)
                tail_ratio = 1.0 - tail_index / max(1, tail_points - 1)
                alpha = freshness * (0.18 + 0.82 * tail_ratio)
                marker_colors.append((1.0, 0.05 + 0.12 * tail_ratio, 0.025, alpha))
                marker_sizes.append((4.5 + 8.0 * strength) * (0.55 + 0.45 * tail_ratio))

        with self._flow_lock:
            self._flows = alive

        if line_segments:
            self.flow_lines.set_data(
                pos=np.asarray(line_segments, dtype=np.float32),
                color=np.asarray(line_colors, dtype=np.float32),
                connect="segments",
            )
            self.flow_lines.visible = True
        else:
            self.flow_lines.visible = False

        if marker_positions:
            self.pulse_markers.set_data(
                pos=np.asarray(marker_positions, dtype=np.float32),
                face_color=np.asarray(marker_colors, dtype=np.float32),
                edge_color=(1.0, 0.26, 0.12, 0.85),
                size=np.asarray(marker_sizes, dtype=np.float32),
                edge_width=0.8,
                symbol="disc",
            )
            self.pulse_markers.visible = True
        else:
            self.pulse_markers.visible = False

    def _update_focus_layers(self) -> None:
        if self.visual is None or self._snapshot is None:
            self._hide_focus_layer(self.selection_lines, self.selection_markers)
            self._hide_focus_layer(self.hover_lines, self.hover_markers)
            return

        if self._selected_uid:
            self._render_node_focus_layer(
                self._selected_uid,
                self.selection_lines,
                self.selection_markers,
                color=(0.25, 0.95, 1.0, 1.0),
            )
        elif self._selected_edge_key:
            self._render_edge_focus_layer(
                self._selected_edge_key,
                self.selection_lines,
                self.selection_markers,
                color=(0.25, 0.95, 1.0, 1.0),
            )
        else:
            self._hide_focus_layer(self.selection_lines, self.selection_markers)

        same_target = (
            self._hover_uid is not None
            and self._hover_uid == self._selected_uid
            or self._hover_edge_key is not None
            and self._hover_edge_key == self._selected_edge_key
        )
        if same_target:
            self._hide_focus_layer(self.hover_lines, self.hover_markers)
        elif self._hover_uid:
            self._render_node_focus_layer(
                self._hover_uid,
                self.hover_lines,
                self.hover_markers,
                color=(1.0, 0.78, 0.20, 1.0),
            )
        elif self._hover_edge_key:
            self._render_edge_focus_layer(
                self._hover_edge_key,
                self.hover_lines,
                self.hover_markers,
                color=(1.0, 0.78, 0.20, 1.0),
            )
        else:
            self._hide_focus_layer(self.hover_lines, self.hover_markers)

    @staticmethod
    def _hide_focus_layer(lines, markers) -> None:
        lines.visible = False
        markers.visible = False

    def _render_node_focus_layer(self, uid, lines, markers, *, color) -> None:
        geometry = build_focus_geometry(self._snapshot, self.visual, uid)
        if geometry.focus_index is None:
            self._hide_focus_layer(lines, markers)
            return
        if len(geometry.segments):
            lines.set_data(
                pos=geometry.segments,
                color=color,
                width=self.settings.focus_line_width,
                connect="segments",
            )
            lines.visible = True
        else:
            lines.visible = False

        indices = (geometry.focus_index, *geometry.neighbor_indices)
        positions = self.visual.positions[list(indices)]
        base_sizes = self.visual.sizes[list(indices)].astype(np.float32, copy=True)
        base_sizes[0] *= self.settings.focus_node_scale
        if len(base_sizes) > 1:
            base_sizes[1:] *= self.settings.focus_neighbor_scale
        self._set_focus_markers(markers, positions, base_sizes, color, primary_count=1)

    def _render_edge_focus_layer(self, key, lines, markers, *, color) -> None:
        geometry = build_edge_focus_geometry(self.visual, key)
        if geometry.edge is None or not len(geometry.segment):
            self._hide_focus_layer(lines, markers)
            return
        lines.set_data(
            pos=geometry.segment,
            color=color,
            width=self.settings.focus_line_width,
            connect="segments",
        )
        lines.visible = True
        indices = list(geometry.endpoint_indices)
        positions = self.visual.positions[indices]
        sizes = self.visual.sizes[indices].astype(np.float32, copy=True)
        sizes *= self.settings.focus_neighbor_scale
        self._set_focus_markers(markers, positions, sizes, color, primary_count=2)

    @staticmethod
    def _set_focus_markers(markers, positions, sizes, color, *, primary_count: int) -> None:
        edge = np.tile(np.asarray(color, dtype=np.float32), (len(positions), 1))
        face = edge.copy()
        face[:, 3] = 0.10
        if len(edge) > primary_count:
            edge[primary_count:, 3] = 0.75
            face[primary_count:, 3] = 0.05
        markers.set_data(
            pos=positions,
            face_color=face,
            edge_color=edge,
            size=sizes,
            edge_width=2.6,
            symbol="disc",
        )
        markers.visible = True

    def reset_camera(self) -> None:
        self.view.camera.set_range()

    def _on_mouse_press(self, event) -> None:
        if event.button != 1 or self.visual is None:
            return
        node_uid = self._pick_node_uid(event.pos)
        if node_uid is not None:
            self._selected_uid = node_uid
            self._selected_edge_key = None
            self.edge_selected.emit("")
            self.node_selected.emit(node_uid)
        else:
            edge_key = self._pick_edge_key(event.pos)
            self._selected_uid = None
            self._selected_edge_key = edge_key
            self.node_selected.emit("")
            self.edge_selected.emit(edge_key or "")
        self._update_focus_layers()
        self.canvas.update()

    def _on_mouse_move(self, event) -> None:
        if getattr(event, "is_dragging", False):
            return
        if not self.settings.hover_enabled or self.visual is None:
            self._set_hover_target(None, None)
            return
        now = monotonic()
        min_interval = 1.0 / max(1, self.settings.hover_pick_hz)
        if now - self._last_hover_pick < min_interval:
            return
        self._last_hover_pick = now
        node_uid = self._pick_node_uid(event.pos)
        if node_uid is not None:
            self._set_hover_target(node_uid, None)
        else:
            self._set_hover_target(None, self._pick_edge_key(event.pos))

    def _set_hover_target(self, uid: str | None, edge_key: str | None) -> None:
        uid = uid or None
        edge_key = edge_key or None
        if uid == self._hover_uid and edge_key == self._hover_edge_key:
            return
        node_changed = uid != self._hover_uid
        edge_changed = edge_key != self._hover_edge_key
        self._hover_uid = uid
        self._hover_edge_key = edge_key
        if node_changed:
            self.node_hovered.emit(uid or "")
        if edge_changed:
            self.edge_hovered.emit(edge_key or "")
        self._update_focus_layers()
        self.canvas.update()

    def _pick_edge_key(self, pos) -> str | None:
        if self.visual is None or not self.visual.edges or not len(self.visual.positions):
            return None
        try:
            transform = self.nodes.get_transform(map_from="visual", map_to="canvas")
            projected = np.asarray(transform.map(self.visual.positions), dtype=np.float64)
            if projected.ndim != 2:
                return None
            if projected.shape[1] >= 4:
                w = projected[:, 3:4]
                valid = np.abs(w[:, 0]) > 1e-12
                projected[valid, :3] /= w[valid]
            return pick_edge_key_2d(
                self.visual,
                projected,
                pos,
                self.settings.edge_pick_radius_px,
            )
        except Exception:
            return None

    def _pick_node_uid(self, pos) -> str | None:
        """Pick a base marker while temporarily hiding every non-picking overlay."""
        if self.visual is None or not self._last_uid_order or not self.nodes.visible:
            return None

        render_size = tuple(int(d * self.canvas.pixel_scale) for d in self.canvas.size)
        if render_size[0] < 3 or render_size[1] < 3:
            return None
        x_pos = int(pos[0] * self.canvas.pixel_scale)
        y_pos = int(render_size[1] - pos[1] * self.canvas.pixel_scale)
        x_pos = max(1, min(render_size[0] - 2, x_pos))
        y_pos = max(1, min(render_size[1] - 2, y_pos))

        other_visuals = (
            self.structural_lines,
            self.relation_lines,
            self.flow_lines,
            self.selection_lines,
            self.selection_markers,
            self.hover_lines,
            self.hover_markers,
            self.pulse_markers,
            self.labels,
        )
        states = tuple(v.visible for v in other_visuals)
        restore_picker = not self._picker.enabled
        for visual in other_visuals:
            visual.visible = False
        self._picker.enabled = True
        self.nodes.update_gl_state(blend=False)
        try:
            picked = self.canvas.render(
                region=(x_pos - 1, y_pos - 1, 3, 3),
                size=(3, 3),
                bgcolor=(0, 0, 0, 0),
                alpha=True,
            )
            marker_idx = int((picked.view(np.uint32) - 1)[1, 1, 0])
        except Exception:
            marker_idx = -1
        finally:
            if restore_picker:
                self._picker.enabled = False
            self.nodes.update_gl_state(blend=True)
            for visual, visible in zip(other_visuals, states):
                visual.visible = visible

        if 0 <= marker_idx < len(self._last_uid_order):
            return self._last_uid_order[marker_idx]
        return None
