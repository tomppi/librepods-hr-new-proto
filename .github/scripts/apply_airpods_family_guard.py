from pathlib import Path
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
path = root / "android/app/src/main/java/me/kavishdevar/librepods/services/AirPodsService.kt"
text = path.read_text()

if "suppressEquivalentModelRefresh" in text:
    print("AirPods family identification guard is already applied")
    raise SystemExit(0)

start_marker = "            override fun onDeviceInformationReceived(deviceInformation: AACPManager.Companion.AirPodsInformation) {"
end_marker = '\n            @SuppressLint("NewApi")'
start = text.index(start_marker)
end = text.index(end_marker, start)

replacement = '''            override fun onDeviceInformationReceived(deviceInformation: AACPManager.Companion.AirPodsInformation) {
                Log.d(
                    "AirPodsParser",
                    "Device Information: name: ${deviceInformation.name}, modelNumber: ${deviceInformation.modelNumber}, manufacturer: ${deviceInformation.manufacturer}, serialNumber: ${deviceInformation.serialNumber}, version1: ${deviceInformation.version1}, version2: ${deviceInformation.version2}, hardwareRevision: ${deviceInformation.hardwareRevision}, updaterIdentifier: ${deviceInformation.updaterIdentifier}, leftSerialNumber: ${deviceInformation.leftSerialNumber}, rightSerialNumber: ${deviceInformation.rightSerialNumber}, version3: ${deviceInformation.version3}"
                )

                val previousModelNumber = config.airpodsModelNumber
                val previousModel = AirPodsModels.getModelByModelNumber(previousModelNumber)
                val incomingModel = AirPodsModels.getModelByModelNumber(deviceInformation.modelNumber)
                val equivalentModelFlip =
                    previousModelNumber.isNotBlank() &&
                        previousModelNumber != deviceInformation.modelNumber &&
                        previousModel != null &&
                        previousModel === incomingModel
                val stableModelNumber =
                    if (equivalentModelFlip) previousModelNumber else deviceInformation.modelNumber
                val otherInformationChanged =
                    config.airpodsName != deviceInformation.name ||
                        config.airpodsManufacturer != deviceInformation.manufacturer ||
                        config.airpodsSerialNumber != deviceInformation.serialNumber ||
                        config.airpodsLeftSerialNumber != deviceInformation.leftSerialNumber ||
                        config.airpodsRightSerialNumber != deviceInformation.rightSerialNumber ||
                        config.airpodsVersion1 != deviceInformation.version1 ||
                        config.airpodsVersion2 != deviceInformation.version2 ||
                        config.airpodsVersion3 != deviceInformation.version3 ||
                        config.airpodsHardwareRevision != deviceInformation.hardwareRevision ||
                        config.airpodsUpdaterIdentifier != deviceInformation.updaterIdentifier
                val suppressEquivalentModelRefresh = equivalentModelFlip && !otherInformationChanged

                if (equivalentModelFlip) {
                    Log.d(
                        TAG,
                        "Keeping established AirPods model $previousModelNumber when counterpart bud reported ${deviceInformation.modelNumber}; both resolve to ${previousModel?.name}"
                    )
                }

                sharedPreferences.edit {
                    putString("name", deviceInformation.name)
                    putString("airpods_model_number", stableModelNumber)
                    putString("airpods_manufacturer", deviceInformation.manufacturer)
                    putString("airpods_serial_number", deviceInformation.serialNumber)
                    putString("airpods_left_serial_number", deviceInformation.leftSerialNumber)
                    putString("airpods_right_serial_number", deviceInformation.rightSerialNumber)
                    putString("airpods_version1", deviceInformation.version1)
                    putString("airpods_version2", deviceInformation.version2)
                    putString("airpods_version3", deviceInformation.version3)
                    putString("airpods_hardware_revision", deviceInformation.hardwareRevision)
                    putString("airpods_updater_identifier", deviceInformation.updaterIdentifier)
                }

                config.airpodsName = deviceInformation.name
                config.airpodsModelNumber = stableModelNumber
                config.airpodsManufacturer = deviceInformation.manufacturer
                config.airpodsSerialNumber = deviceInformation.serialNumber
                config.airpodsLeftSerialNumber = deviceInformation.leftSerialNumber
                config.airpodsRightSerialNumber = deviceInformation.rightSerialNumber
                config.airpodsVersion1 = deviceInformation.version1
                config.airpodsVersion2 = deviceInformation.version2
                config.airpodsVersion3 = deviceInformation.version3
                config.airpodsHardwareRevision = deviceInformation.hardwareRevision
                config.airpodsUpdaterIdentifier = deviceInformation.updaterIdentifier

                val model = AirPodsModels.getModelByModelNumber(stableModelNumber)
                if (model != null) {
                    airpodsInstance = AirPodsInstance(
                        name = config.airpodsName,
                        model = model,
                        actualModelNumber = config.airpodsModelNumber,
                        serialNumber = config.airpodsSerialNumber,
                        leftSerialNumber = config.airpodsLeftSerialNumber,
                        rightSerialNumber = config.airpodsRightSerialNumber,
                        version1 = config.airpodsVersion1,
                        version2 = config.airpodsVersion2,
                        version3 = config.airpodsVersion3,
                    )
                    if (!suppressEquivalentModelRefresh && device != null) {
                        setMetadatas(device!!)
                    }
                }

                if (!suppressEquivalentModelRefresh) {
                    sendBroadcast(
                        Intent(AirPodsNotifications.AIRPODS_INFORMATION_UPDATED).setPackage(
                            packageName
                        )
                    )
                } else {
                    Log.d(
                        TAG,
                        "Suppressed redundant AirPods metadata/UI refresh for equivalent model flip $previousModelNumber -> ${deviceInformation.modelNumber}"
                    )
                }
            }
'''

path.write_text(text[:start] + replacement + text[end:])
print(f"Patched {path}")
