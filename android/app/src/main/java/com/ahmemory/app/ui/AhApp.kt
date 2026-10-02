package com.ahmemory.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import android.view.WindowManager
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.ahmemory.app.data.AhRepository
import com.ahmemory.app.ui.chats.ChatListScreen
import com.ahmemory.app.ui.chats.ChatThreadScreen
import com.ahmemory.app.ui.memory.MemoryScreen
import com.ahmemory.app.ui.settings.SettingsScreen
import com.ahmemory.app.ui.theme.Black
import com.ahmemory.app.ui.theme.Divider
import com.ahmemory.app.ui.theme.TextPrimary
import com.ahmemory.app.ui.theme.TextSecondary

@Composable
fun AhApp(repository: AhRepository, modifier: Modifier = Modifier) {
    val nav = rememberNavController()
    val vm: AhViewModel = viewModel(factory = AhViewModel.Factory(repository))
    val ui by vm.state.collectAsState()
    val view = LocalView.current
    DisposableEffect(ui.starting) {
        val window = (view.context as? android.app.Activity)?.window
        if (ui.starting) {
            window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
        onDispose {
            window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route.orEmpty()
    val chatsSelected = route == "chats" || route.startsWith("chat/")

    Column(
        modifier = modifier
            .background(Black)
            .statusBarsPadding()
            .navigationBarsPadding(),
    ) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            NavHost(navController = nav, startDestination = "chats") {
                composable("chats") {
                    ChatListScreen(
                        viewModel = vm,
                        onOpen = { id -> nav.navigate("chat/$id") },
                        onOpenSettings = {
                            nav.navigate("settings") {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                    )
                }
                composable("chat/{id}") { entry ->
                    val id = entry.arguments?.getString("id").orEmpty()
                    ChatThreadScreen(
                        sessionId = id,
                        viewModel = vm,
                        onBack = { nav.popBackStack() },
                    )
                }
                composable("memory") {
                    MemoryScreen(viewModel = vm)
                }
                composable("settings") {
                    SettingsScreen(viewModel = vm)
                }
            }
        }
        HorizontalDivider(color = Divider, thickness = 1.dp)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp)
                .background(Black)
                .padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TabLabel(
                text = "Чаты",
                selected = chatsSelected,
                onClick = {
                    nav.navigate("chats") {
                        popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
            TabLabel(
                text = "Память",
                selected = route == "memory",
                onClick = {
                    nav.navigate("memory") {
                        popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
            TabLabel(
                text = "Настройки",
                selected = route == "settings",
                onClick = {
                    nav.navigate("settings") {
                        popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
        }
    }
}

@Composable
private fun TabLabel(
    text: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    TextButton(onClick = onClick) {
        Text(
            text = text,
            color = if (selected) TextPrimary else TextSecondary,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}
