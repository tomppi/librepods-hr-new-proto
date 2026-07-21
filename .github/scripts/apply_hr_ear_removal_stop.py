from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
service_path = root / 'android/app/src/main/java/me/kavishdevar/librepods/services/AirPodsService.kt'
viewmodel_path = root / 'android/app/src/main/java/me/kavishdevar/librepods/presentation/viewmodel/AirPodsViewModel.kt'

service = service_path.read_text()
viewmodel = viewmodel_path.read_text()

if 'heartRateEarRemovalStopRunnable' in service:
    raise SystemExit('HR ear-removal stop is already present')

field_marker = '    private var otherDeviceTookOver = false\n'
field_replacement = field_marker + '''    private val heartRateEarRemovalHandler = Handler(Looper.getMainLooper())
    private var heartRateEarRemovalStopRunnable: Runnable? = null
'''
if service.count(field_marker) != 1:
    raise SystemExit('Unexpected otherDeviceTookOver field marker count')
service = service.replace(field_marker, field_replacement, 1)

old_callback = '''            override fun onEarDetectionReceived(earDetection: ByteArray) {
                sendBroadcast(Intent(AirPodsNotifications.EAR_DETECTION_DATA).apply {
                    val list = earDetectionNotification.status
                    val bytes = ByteArray(2)
                    bytes[0] = list[0]
                    bytes[1] = list[1]
                    putExtra("data", bytes)
                }.apply {
                    setPackage(packageName)
                })
                Log.d(
                    "AirPodsParser",
                    "Ear Detection: ${earDetectionNotification.status[0]} ${earDetectionNotification.status[1]}"
                )
                processEarDetectionChange(earDetection)
            }
'''
new_callback = '''            override fun onEarDetectionReceived(earDetection: ByteArray) {
                processEarDetectionChange(earDetection)
                broadcastEarDetectionState()
                Log.d(
                    "AirPodsParser",
                    "Ear Detection: ${earDetectionNotification.status[0]} ${earDetectionNotification.status[1]}"
                )
            }
'''
if service.count(old_callback) != 1:
    raise SystemExit('Unexpected ear-detection callback marker count')
service = service.replace(old_callback, new_callback, 1)

process_marker = '    private fun processEarDetectionChange(earDetection: ByteArray) {\n'
helpers = '''    private fun broadcastEarDetectionState() {
        val status = earDetectionNotification.status
        sendBroadcast(Intent(AirPodsNotifications.EAR_DETECTION_DATA).apply {
            putExtra(
                "data",
                byteArrayOf(
                    status.getOrElse(0) { 0x01.toByte() },
                    status.getOrElse(1) { 0x01.toByte() }
                )
            )
            setPackage(packageName)
        })
    }

    private fun cancelHeartRateEarRemovalStop() {
        heartRateEarRemovalStopRunnable?.let {
            heartRateEarRemovalHandler.removeCallbacks(it)
        }
        heartRateEarRemovalStopRunnable = null
    }

    private fun scheduleHeartRateStopIfEarbudRemoved(inEarData: List<Boolean>) {
        if (inEarData == listOf(true, true)) {
            cancelHeartRateEarRemovalStop()
            return
        }
        if (!::aacpManager.isInitialized || !aacpManager.heartRateStreamingRequested) return
        if (heartRateEarRemovalStopRunnable != null) return

        val stopRunnable = Runnable {
            heartRateEarRemovalStopRunnable = null
            if (!::aacpManager.isInitialized) return@Runnable

            val status = earDetectionNotification.status
            val bothStillInEar =
                status.getOrElse(0) { 0x01.toByte() } == 0x00.toByte() &&
                    status.getOrElse(1) { 0x01.toByte() } == 0x00.toByte()
            if (!bothStillInEar && aacpManager.heartRateStreamingRequested) {
                val stopped = aacpManager.setHeartRateStreaming(false)
                Log.d(
                    TAG,
                    "Stopped RTBuddy heart-rate stream after earbud removal: stopped=$stopped"
                )
                broadcastEarDetectionState()
            }
        }

        heartRateEarRemovalStopRunnable = stopRunnable
        heartRateEarRemovalHandler.postDelayed(stopRunnable, 100L)
    }

'''
if service.count(process_marker) != 1:
    raise SystemExit('Unexpected processEarDetectionChange marker count')
service = service.replace(process_marker, helpers + process_marker, 1)

status_marker = '        earDetectionNotification.setStatus(earDetection)\n'
status_replacement = '''        earDetectionNotification.setStatus(earDetection)
        scheduleHeartRateStopIfEarbudRemoved(
            listOf(
                earDetectionNotification.status.getOrElse(0) { 0x01.toByte() } == 0x00.toByte(),
                earDetectionNotification.status.getOrElse(1) { 0x01.toByte() } == 0x00.toByte()
            )
        )
'''
process_start = service.index(process_marker)
status_index = service.index(status_marker, process_start)
service = service[:status_index] + status_replacement + service[status_index + len(status_marker):]

old_vm = '''                    AirPodsNotifications.EAR_DETECTION_DATA -> {
                        val data = intent.getByteArrayExtra("data") ?: return
                        val anyEarbudInEar = data.size >= 2 &&
                            (data[0] == 0x00.toByte() || data[1] == 0x00.toByte())
                        _uiState.update {
                            it.copy(heartRateEarbudsInEar = anyEarbudInEar)
                        }
                    }
'''
new_vm = '''                    AirPodsNotifications.EAR_DETECTION_DATA -> {
                        val data = intent.getByteArrayExtra("data") ?: return
                        val bothEarbudsInEar = data.size >= 2 &&
                            data[0] == 0x00.toByte() && data[1] == 0x00.toByte()
                        val streamingRequested = service.aacpManager.heartRateStreamingRequested
                        _uiState.update {
                            it.copy(
                                heartRateEarbudsInEar = bothEarbudsInEar,
                                heartRateStreamingEnabled = streamingRequested,
                                heartRateReceiving =
                                    if (streamingRequested) it.heartRateReceiving else false,
                                latestHeartRateBpm =
                                    if (streamingRequested) it.latestHeartRateBpm else null,
                                latestHeartRateSampleMillis =
                                    if (streamingRequested) it.latestHeartRateSampleMillis else null
                            )
                        }
                        if (!streamingRequested) {
                            viewModelScope.launch {
                                flushPendingHeartRateSamplesToHealthConnect()
                            }
                        }
                    }
'''
if viewmodel.count(old_vm) != 1:
    raise SystemExit('Unexpected ViewModel EAR_DETECTION_DATA marker count')
viewmodel = viewmodel.replace(old_vm, new_vm, 1)

service_path.write_text(service)
viewmodel_path.write_text(viewmodel)
print('Applied minimal 100 ms RTBuddy-only HR ear-removal stop')
