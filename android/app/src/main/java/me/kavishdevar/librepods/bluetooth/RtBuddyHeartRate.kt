/*
    LibrePods - AirPods liberated from Apple’s ecosystem
    Copyright (C) 2025 LibrePods contributors

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.
*/

package me.kavishdevar.librepods.bluetooth

data class HeartRateSample(
    val timestampMillis: Long,
    val bpm: Int,
    val payload: ByteArray,
    val statusTail: ByteArray,
    val rawPacket: ByteArray
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is HeartRateSample) return false
        return timestampMillis == other.timestampMillis &&
            bpm == other.bpm &&
            payload.contentEquals(other.payload) &&
            statusTail.contentEquals(other.statusTail) &&
            rawPacket.contentEquals(other.rawPacket)
    }

    override fun hashCode(): Int {
        var result = timestampMillis.hashCode()
        result = 31 * result + bpm
        result = 31 * result + payload.contentHashCode()
        result = 31 * result + statusTail.contentHashCode()
        result = 31 * result + rawPacket.contentHashCode()
        return result
    }
}

internal object RtBuddyHeartRate {
    private const val AACP_HEADER_SIZE = 4
    private const val BUDDY_COMMAND_HEADER_SIZE = 2
    private const val RTBUDDY_HEADER_SIZE = 6
    private const val SENSOR_DATA_WX_DESCRIPTOR = 0x00100000
    private const val HEART_RATE_SERVICE = 19
    private const val HEART_RATE_PAYLOAD_SIZE = 18

    val startCommand: ByteArray
        get() = byteArrayOf(
            AACPManager.Companion.Opcodes.HEADTRACKING, 0x00,
            0x00, 0x00, 0x10, 0x00,
            0x10, 0x00,
            0x08, 0xE3.toByte(), 0x46,
            0x42, 0x0B,
            0x08, 0x13,
            0x10, 0x02,
            0x1A, 0x05,
            0x01, 0x40, 0x42, 0x0F, 0x00
        )

    val stopCommand: ByteArray
        get() = byteArrayOf(
            AACPManager.Companion.Opcodes.HEADTRACKING, 0x00,
            0x00, 0x00, 0x10, 0x00,
            0x10, 0x00,
            0x08, 0xED.toByte(), 0x46,
            0x42, 0x0B,
            0x08, 0x13,
            0x10, 0x02,
            0x1A, 0x05,
            0x01, 0x00, 0x00, 0x00, 0x00
        )

    fun parseSample(packet: ByteArray): HeartRateSample? {
        val rtBuddyStart = AACP_HEADER_SIZE + BUDDY_COMMAND_HEADER_SIZE
        if (packet.size < rtBuddyStart + RTBUDDY_HEADER_SIZE) return null
        if (packet[0] != 0x04.toByte() ||
            packet[1] != 0x00.toByte() ||
            packet[2] != 0x04.toByte() ||
            packet[3] != 0x00.toByte() ||
            packet[4] != AACPManager.Companion.Opcodes.HEADTRACKING
        ) return null

        val descriptor =
            (packet[rtBuddyStart].toInt() and 0xFF) or
                ((packet[rtBuddyStart + 1].toInt() and 0xFF) shl 8) or
                ((packet[rtBuddyStart + 2].toInt() and 0xFF) shl 16) or
                ((packet[rtBuddyStart + 3].toInt() and 0xFF) shl 24)
        if (descriptor != SENSOR_DATA_WX_DESCRIPTOR) return null

        val protobufLength =
            (packet[rtBuddyStart + 4].toInt() and 0xFF) or
                ((packet[rtBuddyStart + 5].toInt() and 0xFF) shl 8)
        if (protobufLength <= 0) return null

        var cursor = rtBuddyStart + RTBUDDY_HEADER_SIZE
        val protobufEnd = cursor + protobufLength
        if (protobufEnd > packet.size) return null

        while (cursor < protobufEnd) {
            val key = readVarint(packet, cursor, protobufEnd) ?: return null
            cursor = key.nextOffset
            val fieldNumber = (key.value ushr 3).toInt()
            val wireType = (key.value and 0x07).toInt()

            if (fieldNumber == 7 && wireType == 2) {
                val length = readVarint(packet, cursor, protobufEnd) ?: return null
                cursor = length.nextOffset
                val commandEnd = cursor + length.value.toInt()
                if (length.value < 0 || commandEnd > protobufEnd) return null

                parseCommand(packet, cursor, commandEnd)?.let { payload ->
                    val bpm = payload[1].toInt() and 0xFF
                    if (bpm !in 1..300) return null
                    return HeartRateSample(
                        timestampMillis = System.currentTimeMillis(),
                        bpm = bpm,
                        payload = payload,
                        statusTail = payload.copyOfRange(payload.size - 3, payload.size),
                        rawPacket = packet.copyOf()
                    )
                }
                cursor = commandEnd
            } else {
                cursor = skipField(packet, cursor, protobufEnd, wireType) ?: return null
            }
        }

        return null
    }

    private fun parseCommand(data: ByteArray, start: Int, end: Int): ByteArray? {
        var cursor = start
        var service: Int? = null
        var payload: ByteArray? = null

        while (cursor < end) {
            val key = readVarint(data, cursor, end) ?: return null
            cursor = key.nextOffset
            val fieldNumber = (key.value ushr 3).toInt()
            val wireType = (key.value and 0x07).toInt()

            when {
                fieldNumber == 1 && wireType == 0 -> {
                    val value = readVarint(data, cursor, end) ?: return null
                    service = value.value.toInt()
                    cursor = value.nextOffset
                }

                fieldNumber == 3 && wireType == 2 -> {
                    val length = readVarint(data, cursor, end) ?: return null
                    cursor = length.nextOffset
                    val payloadEnd = cursor + length.value.toInt()
                    if (length.value < 0 || payloadEnd > end) return null
                    payload = data.copyOfRange(cursor, payloadEnd)
                    cursor = payloadEnd
                }

                else -> {
                    cursor = skipField(data, cursor, end, wireType) ?: return null
                }
            }
        }

        return payload?.takeIf {
            service == HEART_RATE_SERVICE && it.size == HEART_RATE_PAYLOAD_SIZE
        }
    }

    private data class Varint(val value: Long, val nextOffset: Int)

    private fun readVarint(data: ByteArray, start: Int, end: Int): Varint? {
        var value = 0L
        var shift = 0
        var cursor = start

        while (cursor < end && shift < 64) {
            val byte = data[cursor].toInt() and 0xFF
            value = value or ((byte and 0x7F).toLong() shl shift)
            cursor++
            if ((byte and 0x80) == 0) return Varint(value, cursor)
            shift += 7
        }
        return null
    }

    private fun skipField(
        data: ByteArray,
        start: Int,
        end: Int,
        wireType: Int
    ): Int? = when (wireType) {
        0 -> readVarint(data, start, end)?.nextOffset
        1 -> (start + 8).takeIf { it <= end }
        2 -> {
            val length = readVarint(data, start, end) ?: return null
            val next = length.nextOffset + length.value.toInt()
            next.takeIf { length.value >= 0 && it <= end }
        }
        5 -> (start + 4).takeIf { it <= end }
        else -> null
    }
}
