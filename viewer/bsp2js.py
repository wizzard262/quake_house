"""Convert Quake 1 BSP (version 29) maps into data files for viewer.html.

Each map becomes <name>.js holding its triangles, its own textures (decoded with
palette.lmp, the standard Quake palette) and a lightmap atlas of the map's baked
lighting.

Usage:  python bsp2js.py ..\\*.bsp
"""
import base64, glob, json, math, os, re, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
LUMPS = ['entities', 'planes', 'miptex', 'vertices', 'visibility', 'nodes', 'texinfo', 'faces',
         'lighting', 'clipnodes', 'leaves', 'marksurfaces', 'edges', 'surfedges', 'models']
PALETTE = open(os.path.join(HERE, 'palette.lmp'), 'rb').read()
AW = 1024           # lightmap atlas width
NEUTRAL = 116       # lightmap value used for faces with no baked light (renders at about normal brightness)


def png(w, h, rows, color_type):
    raw = b''.join(b'\x00' + r for r in rows)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return 'data:image/png;base64,' + base64.b64encode(
        b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, color_type, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')).decode()


def read_textures(mt):
    """Returns [(name, width, height, png data URL or None)] in miptex order."""
    out = []
    if not mt:
        return out
    n = struct.unpack_from('<i', mt, 0)[0]
    for i in range(n):
        off = struct.unpack_from('<i', mt, 4 + 4 * i)[0]
        if off < 0:
            out.append(('', 16, 16, None))
            continue
        name = mt[off:off + 16].split(b'\x00')[0].decode('latin-1').lower()
        w, h, ofs0 = struct.unpack_from('<3I', mt, off + 16)
        url = None
        if ofs0 and off + ofs0 + w * h <= len(mt):
            px = mt[off + ofs0:off + ofs0 + w * h]
            if name.startswith('sky'):      # sky = two 128x128 halves; show the back layer only
                rows = [b''.join(PALETTE[c * 3:c * 3 + 3] + b'\x00' for c in px[y * w + w // 2:(y + 1) * w]) for y in range(h)]
                w = w // 2
            else:
                # alpha marks Quake's fullbright colours (palette 224-255): lights and button glows ignore shadow
                rows = [b''.join(PALETTE[c * 3:c * 3 + 3] + (b'\xff' if c >= 224 else b'\x00') for c in px[y * w:(y + 1) * w]) for y in range(h)]
            url = png(w, h, rows, 6)
        out.append((name, w, h, url))
    return out


def convert(path):
    data = open(path, 'rb').read()
    version = struct.unpack_from('<i', data, 0)[0]
    if version != 29:
        raise ValueError(f'{path}: BSP version {version}, expected 29')
    lump = {n: struct.unpack_from('<ii', data, 4 + i * 8) for i, n in enumerate(LUMPS)}

    def chunk(n):
        o, l = lump[n]
        return data[o:o + l]

    verts = list(struct.iter_unpack('<3f', chunk('vertices')))
    edges = list(struct.iter_unpack('<2H', chunk('edges')))
    surfedges = [s[0] for s in struct.iter_unpack('<i', chunk('surfedges'))]
    texinfo = [(t[0:4], t[4:8], t[8]) for t in struct.iter_unpack('<8f2i', chunk('texinfo'))]
    faces = list(struct.iter_unpack('<hhihh4Bi', chunk('faces')))
    lighting = chunk('lighting')
    textures = read_textures(chunk('miptex'))
    has_light = len(lighting) > 0
    models = [dict(mins=m[0:3], maxs=m[3:6], origin=m[6:9], head=m[9:13], firstface=m[14], numfaces=m[15])
              for m in struct.iter_unpack('<9f7i', chunk('models'))]
    face_model = [0] * len(faces)
    for mi, m in enumerate(models):
        for f in range(m['firstface'], m['firstface'] + m['numfaces']):
            face_model[f] = mi
    entities = [dict(re.findall(r'"([^"]*)"\s*"([^"]*)"', b))
                for b in chunk('entities').decode('latin-1').split('}') if '"classname"' in b]

    spawn = [0, 0, 0, 0]
    for block in chunk('entities').decode('latin-1').split('}'):
        kv = dict(re.findall(r'"([^"]*)"\s*"([^"]*)"', block))
        if kv.get('classname') in ('info_player_start', 'info_player_deathmatch') and 'origin' in kv:
            x, y, z = map(float, kv['origin'].split())
            spawn = [x, y, z, float(kv.get('angle', 0))]
            if kv['classname'] == 'info_player_start':
                break

    placed = []
    cur_x, cur_y, row_h = 4, 0, 2
    per_tex = {}   # texture index -> list of triangle-vertex tuples

    for fi, (planenum, side, firstedge, numedges, ti, s0, s1, s2, s3, lightofs) in enumerate(faces):
        vec_s, vec_t, mip = texinfo[ti]
        name, tw, th, _ = textures[mip] if 0 <= mip < len(textures) else ('', 16, 16, None)
        if name.startswith('trigger') or name == 'clip':
            continue
        poly = []
        for i in range(numedges):
            se = surfedges[firstedge + i]
            poly.append(verts[edges[se][0]] if se >= 0 else verts[edges[-se][1]])
        if len(poly) < 3:
            continue
        st = [(v[0] * vec_s[0] + v[1] * vec_s[1] + v[2] * vec_s[2] + vec_s[3],
               v[0] * vec_t[0] + v[1] * vec_t[1] + v[2] * vec_t[2] + vec_t[3]) for v in poly]
        lm = [(1.0, 1.0)] * len(poly)  # the NEUTRAL block at (0..2, 0..2)
        if lightofs >= 0 and s0 != 255 and not name.startswith('sky') and not name.startswith('*'):
            smin = min(s for s, t in st); smax = max(s for s, t in st)
            tmin = min(t for s, t in st); tmax = max(t for s, t in st)
            bsmin, btmin = math.floor(smin / 16), math.floor(tmin / 16)
            w = math.ceil(smax / 16) - bsmin + 1
            h = math.ceil(tmax / 16) - btmin + 1
            if lightofs + w * h <= len(lighting) and w <= 64 and h <= 64:
                if cur_x + w + 1 > AW:
                    cur_x, cur_y, row_h = 0, cur_y + row_h + 1, 0
                x0, y0 = cur_x, cur_y
                cur_x += w + 1
                row_h = max(row_h, h)
                placed.append((x0, y0, w, h, lighting[lightofs:lightofs + w * h]))
                lm = [(x0 + s / 16 - bsmin + 0.5, y0 + t / 16 - btmin + 0.5) for s, t in st]
        shade = 1.0
        if not has_light and not name.startswith('sky'):
            # Map compiled without lighting: shade faces by direction so shapes still read.
            a, b, c = poly[0], poly[1], poly[2]
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
            shade = round(0.55 + 0.45 * abs((0.3 * nx + 0.5 * ny + 0.8 * nz) / ln), 3)
        tw_ = tw if not name.startswith('sky') else tw  # sky already halved in read_textures
        corners = [(v, (s / tw_, t / th), l) for v, (s, t), l in zip(poly, st, lm)]
        tris = per_tex.setdefault((face_model[fi], mip), [])
        for i in range(1, len(poly) - 1):
            for k in (0, i, i + 1):
                tris.append((corners[k], shade))

    AH = 1
    while AH < cur_y + row_h + 1:
        AH *= 2
    pix = bytearray(AW * AH)
    for y in range(2):
        for x in range(2):
            pix[y * AW + x] = NEUTRAL
    for x0, y0, w, h, samples in placed:
        for y in range(h):
            pix[(y0 + y) * AW + x0:(y0 + y) * AW + x0 + w] = samples[y * w:(y + 1) * w]

    pos, uv, lmuv, shades = [], [], [], []
    groups = {}    # model index -> [[first vertex, vertex count, material index], ...]
    used = []
    for model, mip in sorted(per_tex):
        tris = per_tex[(model, mip)]
        if mip not in used:
            used.append(mip)
        groups.setdefault(model, []).append([len(pos) // 3, len(tris), used.index(mip)])
        for (v, (u, t), (lx, ly)), sh in tris:
            pos += [round(v[0], 2), round(v[1], 2), round(v[2], 2)]
            uv += [round(u, 5), round(t, 5)]
            lmuv += [round(lx / AW, 6), round(ly / AH, 6)]
            shades.append(sh)

    def b64(fmt, arr):
        return base64.b64encode(struct.pack('<%d%s' % (len(arr), fmt), *arr)).decode()

    name = os.path.splitext(os.path.basename(path))[0]
    # Collision: Quake's own clipping hulls (hull 1 = player-sized), plus hull 0 for water/lava/slime.
    planes = list(struct.iter_unpack('<4fi', chunk('planes')))
    clipnodes = list(struct.iter_unpack('<i2h', chunk('clipnodes')))
    nodes = list(struct.iter_unpack('<i2h6h2H', chunk('nodes')))
    leaves = list(struct.iter_unpack('<2i6h2H4B', chunk('leaves')))
    coll = {
        'planes': b64('f', [x for p in planes for x in p[0:4]]),
        'ptype': b64('i', [p[4] for p in planes]),
        'clip': b64('i', [x for c in clipnodes for x in c]),
        'nodes': b64('i', [x for n in nodes for x in n[0:3]]),
        'leafc': b64('i', [l[0] for l in leaves]),
        'models': [{'mins': m['mins'], 'maxs': m['maxs'], 'head0': m['head'][0], 'head1': m['head'][1]} for m in models],
    }
    out = {'name': name, 'spawn': spawn, 'triangles': len(pos) // 9,
           'pos': b64('f', pos), 'uv': b64('f', uv), 'lmuv': b64('f', lmuv), 'shade': b64('f', shades),
           'groups': groups, 'coll': coll, 'entities': entities,
           'textures': [{'name': textures[m][0], 'url': textures[m][3]} for m in used],
           'lightmap': png(AW, AH, [bytes(pix[y * AW:(y + 1) * AW]) for y in range(AH)], 0)}
    js = 'window.QMAPS = window.QMAPS || {};\nwindow.QMAPS[%s] = %s;\n' % (json.dumps(name), json.dumps(out))
    open(os.path.join(HERE, name + '.js'), 'w').write(js)
    return name, out['triangles'], len(used), sum(1 for m in used if textures[m][3])


if __name__ == '__main__':
    done = []
    for pattern in sys.argv[1:]:
        for p in sorted(glob.glob(pattern)):
            r = convert(p)
            done.append(r[0])
            print('converted %s: %d triangles, %d textures (%d decoded)' % r)
    with open(os.path.join(HERE, 'maps.js'), 'w') as f:
        f.write('window.QMAP_LIST = %s;\n' % json.dumps(done))
