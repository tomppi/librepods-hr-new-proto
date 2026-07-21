from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
aacp_path = root / 'android/app/src/main/java/me/kavishdevar/librepods/bluetooth/AACPManager.kt'
service_path = root / 'android/app/src/main/java/me/kavishdevar/librepods/services/AirPodsService.kt'
viewmodel_path = root / 'android/app/src/main/java/me/kavishdevar/librepods/presentation/viewmodel/AirPodsViewModel.kt'

aacp = aacp_path.read_text()
service = service_path.read_text()
viewmodel = viewmodel_path.read_text()

if 'sendHeartRateStartOnly' in aacp or 'heartRateHandoffPending' in service:
    raise SystemExit('Single-bud HR handoff is already present')

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'Unexpected {label} marker count: {count}')
    return text.replace(old, new, 1)

# AACPManager: parse role/swap events, track samples, and expose RTBuddy start-only.
aacp = replace_once(
    aacp,
    'import android.util.Log\n',
    'import android.os.SystemClock\nimport android.util.Log\n',
    'AACP SystemClock import',
)

aacp = replace_once(
    aacp,
    '''            const val CONTROL_COMMAND: Byte = 0x09
            const val EAR_DETECTION: Byte = 0x06
''',
    '''            const val CONTROL_COMMAND: Byte = 0x09
            const val BUD_ROLE: Byte = 0x08
            const val EAR_DETECTION: Byte = 0x06
            const val BUD_SWAP_2_PROCEDURE: Byte = 0x47
            const val BUD_SWAP_IMMINENT_CONFIRM: Byte = 0x48
            const val BUD_SWAP_2_COMPLETION: Byte = 0x49
            const val BUD_SWAP_COMPLETE_CONFIRM: Byte = 0x4A
''',
    'AACP role opcode',
)

aacp = replace_once(
    aacp,
    '''    @Volatile
    var heartRateStreamingRequested: Boolean = false
        private set
''',
    '''    @Volatile
    var heartRateStreamingRequested: Boolean = false
        private set

    @Volatile
    var lastHeartRateSampleElapsedRealtime: Long = 0L
        private set
''',
    'AACP HR state field',
)

aacp = replace_once(
    aacp,
    '''        fun onDeviceInformationReceived(deviceInformation: AirPodsInformation)
        fun onHeadTrackingReceived(headTracking: ByteArray)
        fun onUnknownPacketReceived(packet: ByteArray)
''',
    '''        fun onDeviceInformationReceived(deviceInformation: AirPodsInformation)
        fun onHeadTrackingReceived(headTracking: ByteArray)
        fun onHeartRateSampleReceived(sample: HeartRateSample)
        fun onBudRoleReceived(role: Int?, budRole: ByteArray)
        fun onBudSwapEventReceived(opcode: Byte, budSwap: ByteArray)
        fun onUnknownPacketReceived(packet: ByteArray)
''',
    'AACP PacketCallback HR role methods',
)

aacp = replace_once(
    aacp,
    '''        RtBuddyHeartRate.parseSample(packet)?.let { sample ->
            if (heartRateStreamingRequested) {
                heartRateSampleCallback?.invoke(sample)
            } else {
                Log.d(TAG, "Ignoring heart-rate sample because streaming is not requested")
            }
            return
        }
''',
    '''        RtBuddyHeartRate.parseSample(packet)?.let { sample ->
            if (heartRateStreamingRequested) {
                lastHeartRateSampleElapsedRealtime = SystemClock.elapsedRealtime()
                callback?.onHeartRateSampleReceived(sample)
                heartRateSampleCallback?.invoke(sample)
            } else {
                Log.d(TAG, "Ignoring heart-rate sample because streaming is not requested")
            }
            return
        }
''',
    'AACP HR sample dispatch',
)

aacp = replace_once(
    aacp,
    '''            Opcodes.EAR_DETECTION -> {
                callback?.onEarDetectionReceived(packet)
            }
''',
    '''            Opcodes.BUD_ROLE -> {
                val role = packet.getOrNull(6)?.toInt()?.and(0xFF)
                Log.d(
                    TAG,
                    "HR-HANDOFF bud-role role=$role raw=${packet.joinToString(" ") { "%02X".format(it) }}"
                )
                callback?.onBudRoleReceived(role, packet)
            }

            Opcodes.BUD_SWAP_2_PROCEDURE,
            Opcodes.BUD_SWAP_IMMINENT_CONFIRM,
            Opcodes.BUD_SWAP_2_COMPLETION,
            Opcodes.BUD_SWAP_COMPLETE_CONFIRM -> {
                Log.d(
                    TAG,
                    "HR-HANDOFF bud-swap opcode=${packet[4].toInt().and(0xFF)} raw=${packet.joinToString(" ") { "%02X".format(it) }}"
                )
                callback?.onBudSwapEventReceived(packet[4], packet)
            }

            Opcodes.EAR_DETECTION -> {
                callback?.onEarDetectionReceived(packet)
            }
''',
    'AACP receive role cases',
)

aacp = replace_once(
    aacp,
    '''    private fun sendHeartRateMonitorEnabled(): Boolean {
        return sendControlCommand(
            ControlCommandIdentifiers.HRM_STATE.value,
            byteArrayOf(0x01, 0x00, 0x00, 0x00)
        )
    }
''',
    '''    fun sendHeartRateStartOnly(): Boolean {
        val started = sendDataPacket(RtBuddyHeartRate.startCommand)
        if (started) heartRateStreamingRequested = true
        return started
    }

    private fun sendHeartRateMonitorEnabled(): Boolean {
        return sendControlCommand(
            ControlCommandIdentifiers.HRM_STATE.value,
            byteArrayOf(0x01, 0x00, 0x00, 0x00)
        )
    }
''',
    'AACP start-only method',
)

aacp = replace_once(
    aacp,
    '''        audioSource = null
        heartRateStreamingRequested = false
''',
    '''        audioSource = null
        heartRateStreamingRequested = false
        lastHeartRateSampleElapsedRealtime = 0L
''',
    'AACP disconnect HR reset',
)

# AirPodsService: replace stop-on-one with passive handoff + start-only recovery.
service = replace_once(
    service,
    'import android.os.ParcelUuid\n',
    'import android.os.ParcelUuid\nimport android.os.SystemClock\n',
    'service SystemClock import',
)

service = replace_once(
    service,
    '''    private val heartRateEarRemovalHandler = Handler(Looper.getMainLooper())
    private var heartRateEarRemovalStopRunnable: Runnable? = null
''',
    '''    private val heartRateHandoffHandler = Handler(Looper.getMainLooper())
    private var heartRateBothOutStopRunnable: Runnable? = null
    private var heartRateHandoffRestartRunnable: Runnable? = null
    @Volatile private var heartRateHandoffPending = false
    private var heartRateHandoffStartedElapsedRealtime = 0L
    private var currentPrimaryBudRole: Int? = null
''',
    'service HR handler fields',
)

service = replace_once(
    service,
    '''            override fun onEarStateChanged(
                device: BLEManager.AirPodsStatus, leftInEar: Boolean, rightInEar: Boolean
            ) {
                Log.d(TAG, "Ear state changed - Left: $leftInEar, Right: $rightInEar")

                // In BLE-only mode, ear detection is purely based on BLE data
''',
    '''            override fun onEarStateChanged(
                device: BLEManager.AirPodsStatus, leftInEar: Boolean, rightInEar: Boolean
            ) {
                Log.d(TAG, "Ear state changed - Left: $leftInEar, Right: $rightInEar")

                val previousInEarData = currentHeartRateInEarData()
                earDetectionNotification.status = listOf(
                    if (leftInEar) 0x00.toByte() else 0x01.toByte(),
                    if (rightInEar) 0x00.toByte() else 0x01.toByte()
                )
                handleHeartRateEarStateChange(previousInEarData, currentHeartRateInEarData())
                broadcastEarDetectionState()

                // In BLE-only mode, ear detection is purely based on BLE data
''',
    'service BLE ear callback',
)

service = replace_once(
    service,
    '''            override fun onProximityKeysReceived(proximityKeys: ByteArray) {
''',
    '''            override fun onHeartRateSampleReceived(sample: AACPManager.HeartRateSample) {
                if (heartRateHandoffPending) {
                    clearHeartRateHandoff("sample_resumed_${sample.bpm}bpm")
                    broadcastEarDetectionState()
                }
            }

            override fun onBudRoleReceived(role: Int?, budRole: ByteArray) {
                val previousRole = currentPrimaryBudRole
                currentPrimaryBudRole = role
                Log.d(
                    TAG,
                    "HR-HANDOFF role previous=$previousRole current=$role pending=$heartRateHandoffPending"
                )
                if (heartRateHandoffPending && role != null && role != previousRole) {
                    scheduleHeartRateStartOnly("bud_role_$role", 100L)
                }
            }

            override fun onBudSwapEventReceived(opcode: Byte, budSwap: ByteArray) {
                Log.d(
                    TAG,
                    "HR-HANDOFF swap opcode=${opcode.toInt().and(0xFF)} pending=$heartRateHandoffPending"
                )
                if (heartRateHandoffPending) {
                    scheduleHeartRateStartOnly(
                        "bud_swap_${opcode.toInt().and(0xFF)}",
                        100L
                    )
                }
            }

            override fun onProximityKeysReceived(proximityKeys: ByteArray) {
''',
    'service HR callback implementations',
)

helper_start = service.index('    private fun cancelHeartRateEarRemovalStop() {')
helper_end = service.index('    private fun processEarDetectionChange(earDetection: ByteArray) {', helper_start)
new_helpers = '''    fun isHeartRateHandoffPending(): Boolean = heartRateHandoffPending

    fun setHeartRateStreamingEnabled(enabled: Boolean): Boolean {
        if (!enabled) {
            cancelHeartRateBothOutStop()
            clearHeartRateHandoff("explicit_stop")
        }

        val changed = aacpManager.setHeartRateStreaming(enabled)
        if (enabled && changed) {
            clearHeartRateHandoff("explicit_start")
        }
        broadcastEarDetectionState()
        return changed
    }

    private fun currentHeartRateInEarData(): List<Boolean> {
        val status = earDetectionNotification.status
        return listOf(
            status.getOrElse(0) { 0x01.toByte() } == 0x00.toByte(),
            status.getOrElse(1) { 0x01.toByte() } == 0x00.toByte()
        )
    }

    private fun currentAnyEarbudInEar(): Boolean = currentHeartRateInEarData().any { it }

    private fun cancelHeartRateBothOutStop() {
        heartRateBothOutStopRunnable?.let { heartRateHandoffHandler.removeCallbacks(it) }
        heartRateBothOutStopRunnable = null
    }

    private fun cancelHeartRateHandoffRestart() {
        heartRateHandoffRestartRunnable?.let { heartRateHandoffHandler.removeCallbacks(it) }
        heartRateHandoffRestartRunnable = null
    }

    private fun clearHeartRateHandoff(reason: String) {
        val wasPending = heartRateHandoffPending
        heartRateHandoffPending = false
        heartRateHandoffStartedElapsedRealtime = 0L
        cancelHeartRateHandoffRestart()
        if (wasPending) Log.d(TAG, "HR-HANDOFF completed/cancelled: $reason")
    }

    private fun beginHeartRateHandoff(reason: String) {
        if (!aacpManager.heartRateStreamingRequested && !heartRateHandoffPending) return

        if (!heartRateHandoffPending) {
            heartRateHandoffPending = true
            heartRateHandoffStartedElapsedRealtime = SystemClock.elapsedRealtime()
            Log.d(TAG, "HR-HANDOFF armed: $reason")
        }

        scheduleHeartRateStartOnly("${reason}_fallback", 250L)
    }

    private fun scheduleHeartRateStartOnly(
        reason: String,
        delayMs: Long,
        attempt: Int = 1
    ) {
        if (!heartRateHandoffPending) return
        cancelHeartRateHandoffRestart()

        val runnable = Runnable {
            heartRateHandoffRestartRunnable = null
            if (!heartRateHandoffPending || !currentAnyEarbudInEar()) return@Runnable

            val lastSample = aacpManager.lastHeartRateSampleElapsedRealtime
            if (lastSample >= heartRateHandoffStartedElapsedRealtime && lastSample != 0L) {
                clearHeartRateHandoff("sample_already_resumed_before_$reason")
                broadcastEarDetectionState()
                return@Runnable
            }

            if (BluetoothConnectionManager.aacpSocket?.isConnected != true) {
                Log.d(TAG, "HR-HANDOFF waiting for fresh AACP socket: $reason")
                return@Runnable
            }

            val started = aacpManager.sendHeartRateStartOnly()
            Log.d(
                TAG,
                "HR-HANDOFF RTBuddy start-only attempt=$attempt reason=$reason started=$started"
            )
            broadcastEarDetectionState()

            if (heartRateHandoffPending && attempt < 2) {
                scheduleHeartRateStartOnly("${reason}_retry", 350L, attempt + 1)
            }
        }

        heartRateHandoffRestartRunnable = runnable
        heartRateHandoffHandler.postDelayed(runnable, delayMs)
    }

    private fun scheduleHeartRateStopIfBothEarbudsRemoved() {
        if (currentAnyEarbudInEar()) {
            cancelHeartRateBothOutStop()
            return
        }
        if (!aacpManager.heartRateStreamingRequested && !heartRateHandoffPending) return
        if (heartRateBothOutStopRunnable != null) return

        val stopRunnable = Runnable {
            heartRateBothOutStopRunnable = null
            if (currentAnyEarbudInEar()) return@Runnable

            val stopped = if (aacpManager.heartRateStreamingRequested) {
                aacpManager.setHeartRateStreaming(false)
            } else {
                true
            }
            clearHeartRateHandoff("both_earbuds_out")
            Log.d(TAG, "Stopped RTBuddy HR because both earbuds are out: stopped=$stopped")
            broadcastEarDetectionState()
        }

        heartRateBothOutStopRunnable = stopRunnable
        heartRateHandoffHandler.postDelayed(stopRunnable, 100L)
    }

    private fun handleHeartRateEarStateChange(
        previousInEarData: List<Boolean>,
        newInEarData: List<Boolean>
    ) {
        val inEarCount = newInEarData.count { it }
        if (inEarCount == 0) {
            scheduleHeartRateStopIfBothEarbudsRemoved()
            return
        }

        cancelHeartRateBothOutStop()
        val removedOneOfTwo = previousInEarData == listOf(true, true) && inEarCount == 1
        if (removedOneOfTwo &&
            (aacpManager.heartRateStreamingRequested || heartRateHandoffPending)
        ) {
            beginHeartRateHandoff("one_earbud_removed")
        } else if (heartRateHandoffPending) {
            scheduleHeartRateStartOnly("ear_state_updated", 100L)
        }
    }

'''
service = service[:helper_start] + new_helpers + service[helper_end:]

service = replace_once(
    service,
    '''        earDetectionNotification.setStatus(earDetection)
        scheduleHeartRateStopIfEarbudRemoved(
            listOf(
                earDetectionNotification.status.getOrElse(0) { 0x01.toByte() } == 0x00.toByte(),
                earDetectionNotification.status.getOrElse(1) { 0x01.toByte() } == 0x00.toByte()
            )
        )
''',
    '''        earDetectionNotification.setStatus(earDetection)
        handleHeartRateEarStateChange(inEarData, currentHeartRateInEarData())
''',
    'service ear-state handoff call',
)

service = replace_once(
    service,
    '''            if (!config.heartRateAutoStartWhenSafe ||
                BluetoothConnectionManager.aacpSocket?.isConnected != true ||
                !anyEarbudInEar ||
                aacpManager.heartRateStreamingRequested
            ) return@launch

            val started = aacpManager.setHeartRateStreaming(true)
''',
    '''            if (!config.heartRateAutoStartWhenSafe ||
                BluetoothConnectionManager.aacpSocket?.isConnected != true ||
                !anyEarbudInEar ||
                aacpManager.heartRateStreamingRequested ||
                heartRateHandoffPending
            ) return@launch

            val started = setHeartRateStreamingEnabled(true)
''',
    'service HR auto-start handoff guard',
)

service = replace_once(
    service,
    '''                    scheduleHeartRateAutoStartWhenSafe()
                    setupStemActions()
''',
    '''                    if (heartRateHandoffPending && currentAnyEarbudInEar()) {
                        scheduleHeartRateStartOnly("fresh_aacp_socket", 250L)
                    }
                    scheduleHeartRateAutoStartWhenSafe()
                    setupStemActions()
''',
    'service fresh socket handoff restart',
)

# ViewModel: keep switch enabled through handoff and route manual start/stop through service.
viewmodel = viewmodel.replace(
    'service.aacpManager.setHeartRateStreaming(false)',
    'service.setHeartRateStreamingEnabled(false)',
)
viewmodel = viewmodel.replace(
    'val started = service.aacpManager.setHeartRateStreaming(true)',
    'val started = service.setHeartRateStreamingEnabled(true)',
)

viewmodel = replace_once(
    viewmodel,
    '''                heartRateStreamingEnabled =
                    service.aacpManager.heartRateStreamingRequested ||
                        it.heartRateStreamingEnabled
''',
    '''                heartRateStreamingEnabled =
                    service.aacpManager.heartRateStreamingRequested ||
                        service.isHeartRateHandoffPending() ||
                        it.heartRateStreamingEnabled
''',
    'ViewModel runtime handoff state',
)

viewmodel = replace_once(
    viewmodel,
    '''                                heartRateStreamingEnabled =
                                    service.aacpManager.heartRateStreamingRequested
''',
    '''                                heartRateStreamingEnabled =
                                    service.aacpManager.heartRateStreamingRequested ||
                                        service.isHeartRateHandoffPending()
''',
    'ViewModel connected handoff state',
)

viewmodel = replace_once(
    viewmodel,
    '''                    AirPodsNotifications.AIRPODS_DISCONNECTED -> {
                        _uiState.update {
                            it.copy(
                                isLocallyConnected = false,
                                heartRateStreamingEnabled = false,
                                heartRateReceiving = false,
                                latestHeartRateBpm = null,
                                latestHeartRateSampleMillis = null
                            )
                        }
''',
    '''                    AirPodsNotifications.AIRPODS_DISCONNECTED -> {
                        val handoffPending = service.isHeartRateHandoffPending()
                        _uiState.update {
                            it.copy(
                                isLocallyConnected = false,
                                heartRateStreamingEnabled = handoffPending,
                                heartRateReceiving = false,
                                latestHeartRateBpm =
                                    if (handoffPending) it.latestHeartRateBpm else null,
                                latestHeartRateSampleMillis =
                                    if (handoffPending) it.latestHeartRateSampleMillis else null
                            )
                        }
''',
    'ViewModel disconnect handoff state',
)

viewmodel = replace_once(
    viewmodel,
    '''                        val bothEarbudsInEar = data.size >= 2 &&
                            data[0] == 0x00.toByte() && data[1] == 0x00.toByte()
                        val streamingRequested = service.aacpManager.heartRateStreamingRequested
                        _uiState.update {
                            it.copy(
                                heartRateEarbudsInEar = bothEarbudsInEar,
''',
    '''                        val anyEarbudInEar = data.size >= 2 &&
                            (data[0] == 0x00.toByte() || data[1] == 0x00.toByte())
                        val streamingRequested =
                            service.aacpManager.heartRateStreamingRequested ||
                                service.isHeartRateHandoffPending()
                        _uiState.update {
                            it.copy(
                                heartRateEarbudsInEar = anyEarbudInEar,
''',
    'ViewModel single-bud ear state',
)

viewmodel = replace_once(
    viewmodel,
    '''                    heartRateStreamingEnabled =
                        service.aacpManager.heartRateStreamingRequested
''',
    '''                    heartRateStreamingEnabled =
                        service.aacpManager.heartRateStreamingRequested ||
                            service.isHeartRateHandoffPending()
''',
    'ViewModel initial handoff state',
)

aacp_path.write_text(aacp)
service_path.write_text(service)
viewmodel_path.write_text(viewmodel)
print('Applied passive single-bud HR handoff with RTBuddy start-only recovery')
