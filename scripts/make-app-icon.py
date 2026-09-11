"""Generate the app's own vector-inspired icon using only the standard library."""
from pathlib import Path
import struct
import zlib


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def make_png(size):
    rows = bytearray()
    points = [(0.13, 0.52), (0.29, 0.52), (0.38, 0.23), (0.52, 0.77), (0.64, 0.39), (0.72, 0.52), (0.87, 0.52)]
    for y in range(size):
        rows.append(0)
        for x in range(size):
            px, py = (x + .5) / size, (y + .5) / size
            distance = 1.
            for (ax, ay), (bx, by) in zip(points, points[1:]):
                dx, dy = bx - ax, by - ay
                t = max(0., min(1., ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
                distance = min(distance, ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** .5)
            rounded = max(abs(px - .5) - .32, 0) ** 2 + max(abs(py - .5) - .32, 0) ** 2 <= .16 ** 2
            color = (227, 255, 241, 255) if distance < .028 else (20, 87, 85, 255)
            rows.extend(color if rounded else (0, 0, 0, 0))
    header = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


def main():
    assets = Path(__file__).resolve().parents[1] / 'desktop' / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    images = [(size, make_png(size)) for size in (16, 32, 48, 64, 128, 256)]
    offset = 6 + 16 * len(images)
    entries = []
    for size, data in images:
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (assets / 'icon.ico').write_bytes(struct.pack('<HHH', 0, 1, len(images)) + b''.join(entries) + b''.join(data for _, data in images))
    (assets / 'icon.png').write_bytes(images[-1][1])


if __name__ == '__main__':
    main()
