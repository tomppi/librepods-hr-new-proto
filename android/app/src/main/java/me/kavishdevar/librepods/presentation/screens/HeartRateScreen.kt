/*
    LibrePods - AirPods liberated from Apple’s ecosystem
    Copyright (C) 2025 LibrePods contributors

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.
*/

package me.kavishdevar.librepods.presentation.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import me.kavishdevar.librepods.health.HealthConnectHeartRateWriter
import me.kavishdevar.librepods.presentation.components.StyledToggle
import me.kavishdevar.librepods.presentation.theme.DesignSystem
import me.kavishdevar.librepods.presentation.theme.LibrePodsTheme
import me.kavishdevar.librepods.presentation.theme.LocalDesignSystem
import me.kavishdevar.librepods.presentation.viewmodel.AirPodsViewModel
import me.kavishdevar.librepods.presentation.viewmodel.demoState

@Composable
fun HeartRateRoute(viewModel: AirPodsViewModel) {
    val state by viewModel.uiState.collectAsState()
    val healthConnectPermissionsLauncher = rememberLauncherForActivityResult(
        contract = HealthConnectHeartRateWriter.requestPermissionContract()
    ) { grantedPermissions ->
        viewModel.setHeartRateHealthConnectSyncEnabled(
            grantedPermissions.containsAll(
                HealthConnectHeartRateWriter.HEART_RATE_WRITE_PERMISSIONS
            )
        )
    }

    LaunchedEffect(Unit) {
        viewModel.refreshHeartRateRuntimeState()
        viewModel.refreshHeartRateHealthConnectStatus()
    }

    val m3eEnabled = LocalDesignSystem.current == DesignSystem.Material
    val topPadding =
        if (m3eEnabled) 0.dp
        else WindowInsets.statusBars.asPaddingValues().calculateTopPadding() + 84.dp
    val bottomPadding =
        if (m3eEnabled) 0.dp
        else WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding() + 12.dp

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.surfaceContainer)
    ) {
        HeartRateScreen(
            enabled = state.heartRateStreamingEnabled,
            latestBpm = state.latestHeartRateBpm,
            receiving = state.heartRateReceiving,
            healthConnectSyncEnabled = state.heartRateHealthConnectSyncEnabled,
            healthConnectAvailable = state.heartRateHealthConnectAvailable,
            autoStartWhenSafe = state.heartRateAutoStartWhenSafe,
            topPadding = topPadding,
            bottomPadding = bottomPadding,
            setEnabled = viewModel::setHeartRateStreamingEnabled,
            setAutoStartWhenSafe = viewModel::setHeartRateAutoStartWhenSafe,
            setHealthConnectSyncEnabled = { enabled ->
                if (enabled) {
                    if (state.heartRateHealthConnectAvailable) {
                        healthConnectPermissionsLauncher.launch(
                            HealthConnectHeartRateWriter.HEART_RATE_WRITE_PERMISSIONS
                        )
                    } else {
                        viewModel.refreshHeartRateHealthConnectStatus()
                    }
                } else {
                    viewModel.setHeartRateHealthConnectSyncEnabled(false)
                }
            }
        )
    }
}

@Composable
fun HeartRateScreen(
    enabled: Boolean,
    latestBpm: Int?,
    receiving: Boolean,
    healthConnectSyncEnabled: Boolean,
    healthConnectAvailable: Boolean,
    autoStartWhenSafe: Boolean,
    topPadding: Dp = 16.dp,
    bottomPadding: Dp = 16.dp,
    setEnabled: (Boolean) -> Unit,
    setAutoStartWhenSafe: (Boolean) -> Unit,
    setHealthConnectSyncEnabled: (Boolean) -> Unit
) {
    val scrollState = rememberScrollState()

    Column(
        modifier = Modifier
            .padding(horizontal = 16.dp)
            .verticalScroll(scrollState),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Spacer(modifier = Modifier.height(topPadding))

        StyledToggle(
            label = "AirPods heart rate",
            checked = enabled,
            onCheckedChange = setEnabled
        )

        StyledToggle(
            label = "Start when AirPods connect safely",
            checked = autoStartWhenSafe,
            onCheckedChange = setAutoStartWhenSafe
        )

        StyledToggle(
            label = "Sync to Health Connect",
            checked = healthConnectSyncEnabled,
            enabled = healthConnectAvailable,
            onCheckedChange = setHealthConnectSyncEnabled
        )

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(28.dp))
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = latestBpm?.let { "$it BPM" } ?: "No heart-rate sample yet",
                style = MaterialTheme.typography.headlineLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = if (receiving) "Receiving now" else "Not receiving",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.65f)
            )
        }

        Spacer(modifier = Modifier.height(bottomPadding))
    }
}

@Preview(name = "Heart rate")
@Composable
private fun HeartRateScreenPreview() {
    LibrePodsTheme(m3eEnabled = false) {
        Box(modifier = Modifier.background(MaterialTheme.colorScheme.surfaceContainer)) {
            HeartRateScreen(
                enabled = true,
                latestBpm = demoState.latestHeartRateBpm,
                receiving = true,
                healthConnectSyncEnabled = demoState.heartRateHealthConnectSyncEnabled,
                healthConnectAvailable = demoState.heartRateHealthConnectAvailable,
                autoStartWhenSafe = demoState.heartRateAutoStartWhenSafe,
                setEnabled = {},
                setAutoStartWhenSafe = {},
                setHealthConnectSyncEnabled = {},
                bottomPadding = 16.dp
            )
        }
    }
}
