from pathlib import Path

service_path = Path("android/app/src/main/java/me/kavishdevar/librepods/services/AirPodsService.kt")
manager_path = Path("android/app/src/main/java/me/kavishdevar/librepods/bluetooth/AACPManager.kt")
viewmodel_path = Path("android/app/src/main/java/me/kavishdevar/librepods/presentation/viewmodel/AirPodsViewModel.kt")

manager = manager_path.read_text()

old = '''    @Volatile
    var heartRateStreamingRequested: Boolean = false
        private set

'''
new = '''    @Volatile
    var heartRateStreamingRequested: Boolean = false
        private set

    @Volatile
    private var preserveHeartRateRequestUntilMs: Long = 0L

    fun preserveHeartRateStreamingRequestForRoleMigration(durationMs: Long) {
        if (!heartRateStreamingRequested) return
        val until = System.currentTimeMillis() + durationMs.coerceAtLeast(0L)
        preserveHeartRateRequestUntilMs = maxOf(preserveHeartRateRequestUntilMs, until)
        Log.d(
            TAG,
            "HR-BUD-MIGRATION preserving requested state for ${durationMs}ms without sending commands"
        )
    }

    fun clearHeartRateRoleMigrationPreservation() {
        preserveHeartRateRequestUntilMs = 0L
    }

    fun isHeartRateRoleMigrationPreservationActive(): Boolean =
        heartRateStreamingRequested && System.currentTimeMillis() <= preserveHeartRateRequestUntilMs

'''
if manager.count(old) != 1:
    raise SystemExit("AACPManager heart-rate state block mismatch")
manager = manager.replace(old, new, 1)

old = '''    fun setHeartRateStreaming(enabled: Boolean): Boolean {
        return if (enabled) {
            val controlOk = sendHeartRateMonitorEnabled()
            val startOk = sendDataPacket(RtBuddyHeartRate.startCommand)
            val started = controlOk && startOk
            if (started) heartRateStreamingRequested = true
            started
        } else {
            val stopped = sendDataPacket(RtBuddyHeartRate.stopCommand)
            heartRateStreamingRequested = false
            stopped
        }
    }
'''
new = '''    fun setHeartRateStreaming(enabled: Boolean): Boolean {
        return if (enabled) {
            clearHeartRateRoleMigrationPreservation()
            val controlOk = sendHeartRateMonitorEnabled()
            val startOk = sendDataPacket(RtBuddyHeartRate.startCommand)
            val started = controlOk && startOk
            if (started) heartRateStreamingRequested = true
            started
        } else {
            clearHeartRateRoleMigrationPreservation()
            val stopped = sendDataPacket(RtBuddyHeartRate.stopCommand)
            heartRateStreamingRequested = false
            stopped
        }
    }
'''
if manager.count(old) != 1:
    raise SystemExit("AACPManager setHeartRateStreaming block mismatch")
manager = manager.replace(old, new, 1)

old = '''    fun disconnected() {
        Log.d(TAG, "Disconnected, clearing state")
        controlCommandStatusList.clear()
        controlCommandListeners.clear()
        owns = false
        oldConnectedDevices = listOf()
        connectedDevices = listOf()
        audioSource = null
        heartRateStreamingRequested = false
    }
'''
new = '''    fun disconnected() {
        val preserveHeartRateRequest = isHeartRateRoleMigrationPreservationActive()
        Log.d(
            TAG,
            "Disconnected, clearing state; preserveHeartRateRequest=$preserveHeartRateRequest"
        )
        controlCommandStatusList.clear()
        controlCommandListeners.clear()
        owns = false
        oldConnectedDevices = listOf()
        connectedDevices = listOf()
        audioSource = null
        if (!preserveHeartRateRequest) {
            heartRateStreamingRequested = false
            clearHeartRateRoleMigrationPreservation()
        } else {
            Log.d(
                TAG,
                "HR-BUD-MIGRATION kept requested state across AACP disconnect without restarting HR"
            )
        }
    }
'''
if manager.count(old) != 1:
    raise SystemExit("AACPManager disconnected block mismatch")
manager = manager.replace(old, new, 1)
manager_path.write_text(manager)

service = service_path.read_text()

old = '''    private val heartRateEarRemovalHandler = Handler(Looper.getMainLooper())
    private var heartRateEarRemovalStopRunnable: Runnable? = null
    private var currentPrimaryBudRole: Int? = null
'''
new = '''    private val heartRateEarRemovalHandler = Handler(Looper.getMainLooper())
    private var heartRateEarRemovalStopRunnable: Runnable? = null
    private var currentPrimaryBudRole: Int? = null
    private var acceptedPrimaryBudRole: Int? = null
    @Volatile
    private var roleMigrationPreserveUntilMs: Long = 0L
'''
if service.count(old) != 1:
    raise SystemExit("AirPodsService role fields block mismatch")
service = service.replace(old, new, 1)

old = '''        sharedPreferences = getSharedPreferences("settings", MODE_PRIVATE)
        initializeConfig()
'''
new = '''        sharedPreferences = getSharedPreferences("settings", MODE_PRIVATE)
        acceptedPrimaryBudRole =
            sharedPreferences.getInt("accepted_primary_bud_role", 0)
                .takeIf { it == 0x01 || it == 0x02 }
        currentPrimaryBudRole = acceptedPrimaryBudRole
        initializeConfig()
'''
if service.count(old) < 1:
    raise SystemExit("AirPodsService settings initialization block missing")
service = service.replace(old, new, 1)

callback_start = service.index("            override fun onBudRoleReceived(role: Int?, budRole: ByteArray) {")
callback_end = service.index("            override fun onProximityKeysReceived", callback_start)
new_callbacks = '''            override fun onBudRoleReceived(role: Int?, budRole: ByteArray) {
                val previousReportedRole = currentPrimaryBudRole
                val previousAcceptedRole = acceptedPrimaryBudRole
                currentPrimaryBudRole = role

                if (role == 0x01 || role == 0x02) {
                    acceptedPrimaryBudRole = role
                    sharedPreferences.edit {
                        putInt("accepted_primary_bud_role", role)
                    }
                }

                val acceptedRole = acceptedPrimaryBudRole
                val changed =
                    previousAcceptedRole != null &&
                        acceptedRole != null &&
                        previousAcceptedRole != acceptedRole

                if (changed) {
                    armRoleMigrationPreservation(
                        "bud_role_${budRoleName(previousAcceptedRole)}_to_${budRoleName(acceptedRole)}"
                    )
                }

                Log.d(
                    TAG,
                    "HR-BUD-MIGRATION reportedPrevious=${budRoleName(previousReportedRole)} " +
                        "acceptedPrevious=${budRoleName(previousAcceptedRole)} " +
                        "acceptedCurrent=${budRoleName(acceptedRole)} changed=$changed " +
                        "primaryInEar=${acceptedPrimaryBudInEar()} " +
                        "streamingRequested=${aacpManager.heartRateStreamingRequested}"
                )
            }

            override fun onBudSwapEventReceived(opcode: Byte, budSwap: ByteArray) {
                val opcodeValue = opcode.toInt().and(0xFF)
                armRoleMigrationPreservation("bud_swap_%02X".format(opcodeValue))
                Log.d(
                    TAG,
                    "HR-BUD-MIGRATION swap opcode=$opcodeValue " +
                        "accepted=${budRoleName(acceptedPrimaryBudRole)} " +
                        "streamingRequested=${aacpManager.heartRateStreamingRequested}"
                )
            }

'''
service = service[:callback_start] + new_callbacks + service[callback_end:]

marker = '''    private fun cancelHeartRateEarRemovalStop() {
'''
helpers = '''    private fun budRoleName(role: Int?): String = when (role) {
        0x01 -> "left_primary"
        0x02 -> "right_primary"
        null -> "unknown"
        else -> "unknown_$role"
    }

    private fun anyEarbudInEar(): Boolean {
        val status = earDetectionNotification.status
        return status.getOrElse(0) { 0x01.toByte() } == 0x00.toByte() ||
            status.getOrElse(1) { 0x01.toByte() } == 0x00.toByte()
    }

    private fun acceptedPrimaryBudInEar(): Boolean? {
        val status = earDetectionNotification.status
        return when (acceptedPrimaryBudRole) {
            0x01 -> status.getOrElse(0) { 0x01.toByte() } == 0x00.toByte()
            0x02 -> status.getOrElse(1) { 0x01.toByte() } == 0x00.toByte()
            else -> null
        }
    }

    private fun armRoleMigrationPreservation(reason: String) {
        if (!::aacpManager.isInitialized || !aacpManager.heartRateStreamingRequested) {
            Log.d(
                TAG,
                "HR-BUD-MIGRATION not armed because HR is not requested: reason=$reason"
            )
            return
        }
        if (!anyEarbudInEar()) {
            Log.d(
                TAG,
                "HR-BUD-MIGRATION not armed because both earbuds are out-of-ear: reason=$reason"
            )
            return
        }

        val durationMs = 10_000L
        roleMigrationPreserveUntilMs =
            maxOf(roleMigrationPreserveUntilMs, System.currentTimeMillis() + durationMs)
        aacpManager.preserveHeartRateStreamingRequestForRoleMigration(durationMs)
        Log.d(
            TAG,
            "HR-BUD-MIGRATION armed for ${durationMs}ms: reason=$reason " +
                "accepted=${budRoleName(acceptedPrimaryBudRole)} " +
                "primaryInEar=${acceptedPrimaryBudInEar()}"
        )
    }

    fun shouldPreserveHeartRateUiForRoleMigration(): Boolean =
        ::aacpManager.isInitialized &&
            aacpManager.heartRateStreamingRequested &&
            aacpManager.isHeartRateRoleMigrationPreservationActive() &&
            System.currentTimeMillis() <= roleMigrationPreserveUntilMs

'''
if service.count(marker) != 1:
    raise SystemExit("AirPodsService helper insertion marker mismatch")
service = service.replace(marker, helpers + marker, 1)

old = '''            if (bothStillOutOfEar && aacpManager.heartRateStreamingRequested) {
                val stopped = aacpManager.setHeartRateStreaming(false)
'''
new = '''            if (bothStillOutOfEar && aacpManager.heartRateStreamingRequested) {
                roleMigrationPreserveUntilMs = 0L
                aacpManager.clearHeartRateRoleMigrationPreservation()
                val stopped = aacpManager.setHeartRateStreaming(false)
'''
if service.count(old) != 1:
    raise SystemExit("AirPodsService both-out stop block mismatch")
service = service.replace(old, new, 1)
service_path.write_text(service)

viewmodel = viewmodel_path.read_text()
old = '''                    AirPodsNotifications.AIRPODS_DISCONNECTED -> {
                        _uiState.update {
                            it.copy(
                                isLocallyConnected = false,
                                heartRateStreamingEnabled = false,
                                heartRateReceiving = false,
                                latestHeartRateBpm = null,
                                latestHeartRateSampleMillis = null
                            )
                        }
                        viewModelScope.launch {
                            flushPendingHeartRateSamplesToHealthConnect()
                        }
                    }
'''
new = '''                    AirPodsNotifications.AIRPODS_DISCONNECTED -> {
                        val preserveRoleMigration =
                            service.shouldPreserveHeartRateUiForRoleMigration()
                        _uiState.update { state ->
                            if (preserveRoleMigration) {
                                state.copy(
                                    isLocallyConnected = false,
                                    heartRateStreamingEnabled = true,
                                    heartRateReceiving = false
                                )
                            } else {
                                state.copy(
                                    isLocallyConnected = false,
                                    heartRateStreamingEnabled = false,
                                    heartRateReceiving = false,
                                    latestHeartRateBpm = null,
                                    latestHeartRateSampleMillis = null
                                )
                            }
                        }
                        if (!preserveRoleMigration) {
                            viewModelScope.launch {
                                flushPendingHeartRateSamplesToHealthConnect()
                            }
                        }
                    }
'''
if viewmodel.count(old) != 1:
    raise SystemExit("AirPodsViewModel disconnect block mismatch")
viewmodel = viewmodel.replace(old, new, 1)
viewmodel_path.write_text(viewmodel)
