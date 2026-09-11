import io
from pathlib import Path
import struct
import sys
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import hantek_scope as scope

def frame(payload):
    data = b'\x53' + struct.pack('<H', len(payload) + 2) + b'\x90' + payload
    return data + bytes([sum(data) & 255])

class DescriptionChecks(unittest.TestCase):
    def test_only_fixed_read_path(self):
        self.assertEqual(scope.request_packet(0x10, scope.PROTOCOL_PATH_PAYLOAD)[3:-1], b'\x10\x00/protocol.inf')
        for payload in (b'', b'\x00/etc/passwd', b'/protocol.inf', b'\x00/protocol.inf\x00', b'\x00/../protocol.inf'):
            with self.assertRaises(scope.ScopeError): scope.request_packet(0x10, payload)

    def test_fragmented_description_and_bulk_checksum(self):
        data = b'[TOTAL] 3\n[A] 1\n[B] 2\n'
        wire = frame(b'\x01' + data) + frame(bytes([2, sum(data) & 255]))
        blocks = iter([wire[:2], wire[2:6], wire[6:]])
        raw = io.BytesIO()
        self.assertEqual(scope.protocol_bytes(scope.FrameReader(lambda: next(blocks), time.monotonic()+2), raw), data)
        self.assertEqual(raw.getvalue(), data)
        for payload in (b'\x02\x00', b'\x03', b'\x01' + b'x' * (scope.MAX_PROTOCOL_BYTES+1)):
            blocks = iter([frame(payload)])
            with self.assertRaises(scope.ScopeError):
                scope.protocol_bytes(scope.FrameReader(lambda: next(blocks), time.monotonic()+2), io.BytesIO())

if __name__ == '__main__': unittest.main()
