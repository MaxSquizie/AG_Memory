from __future__ import annotations

from dataclasses import dataclass
import hashlib
from math import pi

import numpy as np

from ah.config import GUISettings
from ah.diagnostics import GraphSnapshot


@dataclass(frozen=True, slots=True)
class VisualEdge:
    key: str
    uid: str | None
    source_uid: str
    target_uid: str
    relation_id: str
    edge_kind: str
    canonical_link: bool


@dataclass(frozen=True, slots=True)
class VisualGraph:
    node_uids: tuple[str, ...]
    positions: np.ndarray
    face_colors: np.ndarray
    edge_colors: np.ndarray
    sizes: np.ndarray
    workspace_mask: np.ndarray
    activation_mask: np.ndarray
    relation_segments: np.ndarray
    relation_colors: np.ndarray
    structural_segments: np.ndarray
    structural_colors: np.ndarray
    edges: tuple[VisualEdge, ...]

    @property
    def node_index(self) -> dict[str, int]:
        return {uid: i for i, uid in enumerate(self.node_uids)}

    @property
    def edge_index(self) -> dict[str, VisualEdge]:
        return {edge.key: edge for edge in self.edges}


@dataclass(frozen=True, slots=True)
class FocusGeometry:
    focus_index: int | None
    neighbor_indices: tuple[int, ...]
    segments: np.ndarray


@dataclass(frozen=True, slots=True)
class EdgeFocusGeometry:
    edge: VisualEdge | None
    endpoint_indices: tuple[int, ...]
    segment: np.ndarray


def build_focus_geometry(snapshot: GraphSnapshot, visual: VisualGraph, uid: str | None) -> FocusGeometry:
    """Return all immediate incoming/outgoing geometry for a focused node."""
    if not uid:
        return FocusGeometry(None, (), np.empty((0, 3), dtype=np.float32))
    index = visual.node_index
    focus_index = index.get(uid)
    if focus_index is None:
        return FocusGeometry(None, (), np.empty((0, 3), dtype=np.float32))

    neighbors: set[int] = set()
    segments: list[np.ndarray] = []
    for edge in visual.edges:
        if edge.source_uid != uid and edge.target_uid != uid:
            continue
        source_index = index.get(edge.source_uid)
        target_index = index.get(edge.target_uid)
        if source_index is None or target_index is None:
            continue
        other_index = target_index if edge.source_uid == uid else source_index
        if other_index != focus_index:
            neighbors.add(other_index)
        segments.extend((visual.positions[source_index], visual.positions[target_index]))

    segment_array = (
        np.asarray(segments, dtype=np.float32)
        if segments
        else np.empty((0, 3), dtype=np.float32)
    )
    return FocusGeometry(focus_index, tuple(sorted(neighbors)), segment_array)


def build_edge_focus_geometry(visual: VisualGraph, key: str | None) -> EdgeFocusGeometry:
    if not key:
        return EdgeFocusGeometry(None, (), np.empty((0, 3), dtype=np.float32))
    edge = visual.edge_index.get(key)
    if edge is None:
        return EdgeFocusGeometry(None, (), np.empty((0, 3), dtype=np.float32))
    index = visual.node_index
    source_index = index.get(edge.source_uid)
    target_index = index.get(edge.target_uid)
    if source_index is None or target_index is None:
        return EdgeFocusGeometry(None, (), np.empty((0, 3), dtype=np.float32))
    segment = np.asarray(
        (visual.positions[source_index], visual.positions[target_index]),
        dtype=np.float32,
    )
    return EdgeFocusGeometry(edge, (source_index, target_index), segment)


def point_segment_distance_2d(point: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Screen-space distance from a point to a finite segment."""
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom <= 1e-12:
        return float(np.linalg.norm(point - a))
    t = float(np.dot(point - a, ab) / denom)
    t = max(0.0, min(1.0, t))
    nearest = a + ab * t
    return float(np.linalg.norm(point - nearest))


def pick_edge_key_2d(
    visual: VisualGraph,
    projected_positions: np.ndarray,
    point: tuple[float, float] | np.ndarray,
    tolerance_px: float,
) -> str | None:
    """Pick the nearest visible edge in already-projected canvas coordinates.

    Canonical L wins a tie against a structural diagnostic edge occupying the same
    screen segment. This helper is VisPy-independent and unit-testable.
    """
    if tolerance_px <= 0 or len(projected_positions) != len(visual.node_uids):
        return None
    p = np.asarray(point, dtype=np.float64)[:2]
    index = visual.node_index
    best: tuple[float, int, str] | None = None
    for edge in visual.edges:
        si = index.get(edge.source_uid)
        ti = index.get(edge.target_uid)
        if si is None or ti is None:
            continue
        a = np.asarray(projected_positions[si], dtype=np.float64)[:2]
        b = np.asarray(projected_positions[ti], dtype=np.float64)[:2]
        if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
            continue
        distance = point_segment_distance_2d(p, a, b)
        if distance > tolerance_px:
            continue
        tie_priority = 0 if edge.canonical_link else 1
        candidate = (distance, tie_priority, edge.key)
        if best is None or candidate < best:
            best = candidate
    return None if best is None else best[2]


class GraphLayout:
    """Stable deterministic 2.5D/3D layout; positions never enter AH semantics."""

    _DOMAIN_Z = {None: -1.5, "C": -0.5, "P": 0.5, "H": 1.5}

    def positions(self, snapshot: GraphSnapshot, settings: GUISettings) -> np.ndarray:
        out = np.zeros((len(snapshot.nodes), 3), dtype=np.float32)
        for i, node in enumerate(snapshot.nodes):
            digest = hashlib.blake2b(node.uid.encode("utf-8"), digest_size=16).digest()
            a = int.from_bytes(digest[0:4], "little") / 2**32
            r = int.from_bytes(digest[4:8], "little") / 2**32
            j = int.from_bytes(digest[8:12], "little") / 2**32
            angle = 2 * pi * a
            radius = 2.0 + 11.0 * (r ** 0.65)
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)
            base_z = self._DOMAIN_Z.get(node.domain, 0.0) * settings.domain_z_spacing
            if settings.render_mode == "3d":
                z = base_z + (j - 0.5) * settings.domain_z_spacing * 0.8
            else:
                z = base_z
            out[i] = (x, y, z)
        return out


class GraphVisualMapper:
    """Map read-only runtime diagnostics to GPU-friendly arrays and edge metadata."""

    _BASE = {
        None: np.array([0.30, 0.72, 0.48], dtype=np.float32),
        "C": np.array([0.18, 0.62, 1.00], dtype=np.float32),
        "P": np.array([0.76, 0.34, 1.00], dtype=np.float32),
        "H": np.array([1.00, 0.58, 0.18], dtype=np.float32),
    }
    _EXCITED_DARK = np.array([0.38, 0.015, 0.02], dtype=np.float32)
    _EXCITED_HOT = np.array([1.00, 0.11, 0.035], dtype=np.float32)
    _EXCITED_PEAK = np.array([1.00, 0.48, 0.20], dtype=np.float32)

    def __init__(self, layout: GraphLayout | None = None) -> None:
        self.layout = layout or GraphLayout()

    def build(
        self,
        snapshot: GraphSnapshot,
        settings: GUISettings,
        *,
        x_max: float,
    ) -> VisualGraph:
        positions = self.layout.positions(snapshot, settings)
        node_uids = tuple(node.uid for node in snapshot.nodes)
        index = {uid: i for i, uid in enumerate(node_uids)}
        n = len(node_uids)
        face = np.zeros((n, 4), dtype=np.float32)
        edge = np.zeros((n, 4), dtype=np.float32)
        sizes = np.zeros((n,), dtype=np.float32)
        workspace = np.zeros((n,), dtype=bool)
        activated = np.zeros((n,), dtype=bool)

        denom = max(float(x_max), 1e-9)
        excitation_by_uid: dict[str, float] = {}
        for i, node in enumerate(snapshot.nodes):
            x = max(0.0, float(node.excitation or 0.0))
            activation = min(1.0, x / denom) ** settings.excitation_gamma
            excitation_by_uid[node.uid] = activation
            base = self._BASE.get(node.domain, self._BASE[None])
            if activation > 0:
                # Runtime excitation is a red heat overlay. At low residual x the
                # muted domain hue is still readable; strong excitation converges to
                # a domain-independent red/orange heat scale. This avoids a tiny
                # asymptotic x turning the whole graph uniformly red forever.
                hot = self._EXCITED_DARK * (1.0 - activation) + self._EXCITED_HOT * activation
                if activation > 0.82:
                    peak = (activation - 0.82) / 0.18
                    hot = hot * (1.0 - peak) + self._EXCITED_PEAK * peak
                heat = min(1.0, activation * 1.25)
                rgb = (base * 0.34) * (1.0 - heat) + hot * heat
            else:
                rgb = base * 0.34
            face[i, :3] = np.clip(rgb, 0.0, 1.0)
            face[i, 3] = 0.96 if activation > 0 else 0.50
            workspace[i] = bool(node.in_workspace)
            activated[i] = bool(node.activation_event)

            if activated[i]:
                edge[i] = (1.0, 1.0, 1.0, 1.0)
            elif workspace[i]:
                edge[i] = (0.45, 1.0, 1.0, 1.0)
            elif node.uid in snapshot.pending_incoming:
                edge[i] = (1.0, 0.85, 0.25, 0.95)
            else:
                edge[i] = (*base, 0.36)

            sizes[i] = settings.node_size_min + (
                settings.node_size_max - settings.node_size_min
            ) * activation
            if activated[i]:
                sizes[i] = min(settings.node_size_max * 1.25, sizes[i] * 1.25)

        relation_segments: list[np.ndarray] = []
        relation_colors: list[np.ndarray] = []
        structural_segments: list[np.ndarray] = []
        structural_colors: list[np.ndarray] = []
        visual_edges: list[VisualEdge] = []

        if settings.show_relation_edges:
            for link in snapshot.links:
                if link.source_uid not in index or link.target_uid not in index:
                    continue
                relation_segments.extend((positions[index[link.source_uid]], positions[index[link.target_uid]]))
                alpha = 0.10 + 0.70 * max(0.0, min(1.0, link.weight))
                adjacent_x = max(
                    excitation_by_uid.get(link.source_uid, 0.0),
                    excitation_by_uid.get(link.target_uid, 0.0),
                )
                if adjacent_x > 0:
                    rgb = np.array([0.48, 0.015, 0.02], dtype=np.float32) * (1.0 - adjacent_x) + np.array([1.0, 0.12, 0.035], dtype=np.float32) * adjacent_x
                    alpha = max(alpha, 0.30 + 0.65 * adjacent_x)
                else:
                    rgb = np.array([0.30, 0.72, 1.0], dtype=np.float32)
                c = np.array([rgb[0], rgb[1], rgb[2], alpha], dtype=np.float32)
                relation_colors.extend((c, c.copy()))
                visual_edges.append(
                    VisualEdge(
                        key=f"L:{link.uid}",
                        uid=link.uid,
                        source_uid=link.source_uid,
                        target_uid=link.target_uid,
                        relation_id=link.relation_id,
                        edge_kind="L",
                        canonical_link=True,
                    )
                )

        if settings.show_structural_edges:
            for rel in snapshot.structural_edges:
                if rel.source_uid not in index or rel.target_uid not in index:
                    continue
                structural_segments.extend((positions[index[rel.source_uid]], positions[index[rel.target_uid]]))
                adjacent_x = max(
                    excitation_by_uid.get(rel.source_uid, 0.0),
                    excitation_by_uid.get(rel.target_uid, 0.0),
                )
                if adjacent_x > 0:
                    rgb = np.array([0.42, 0.01, 0.02], dtype=np.float32) * (1.0 - adjacent_x) + np.array([0.92, 0.075, 0.035], dtype=np.float32) * adjacent_x
                    alpha = 0.18 + 0.55 * adjacent_x
                else:
                    rgb = np.array([0.62, 0.64, 0.68], dtype=np.float32)
                    alpha = 0.18
                c = np.array([rgb[0], rgb[1], rgb[2], alpha], dtype=np.float32)
                structural_colors.extend((c, c.copy()))
                key = (
                    f"STRUCT:{rel.edge_kind}:{rel.source_uid}:{rel.target_uid}:"
                    f"{rel.relation_id}"
                )
                visual_edges.append(
                    VisualEdge(
                        key=key,
                        uid=None,
                        source_uid=rel.source_uid,
                        target_uid=rel.target_uid,
                        relation_id=rel.relation_id,
                        edge_kind=rel.edge_kind,
                        canonical_link=False,
                    )
                )

        def arr3(values: list[np.ndarray]) -> np.ndarray:
            return (
                np.asarray(values, dtype=np.float32)
                if values
                else np.empty((0, 3), dtype=np.float32)
            )

        def arr4(values: list[np.ndarray]) -> np.ndarray:
            return (
                np.asarray(values, dtype=np.float32)
                if values
                else np.empty((0, 4), dtype=np.float32)
            )

        return VisualGraph(
            node_uids=node_uids,
            positions=positions,
            face_colors=face,
            edge_colors=edge,
            sizes=sizes,
            workspace_mask=workspace,
            activation_mask=activated,
            relation_segments=arr3(relation_segments),
            relation_colors=arr4(relation_colors),
            structural_segments=arr3(structural_segments),
            structural_colors=arr4(structural_colors),
            edges=tuple(visual_edges),
        )
