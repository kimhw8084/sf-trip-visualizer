(() => {
  // .tools/jsdeps/node_modules/fflate/esm/browser.js
  var u8 = Uint8Array;
  var u16 = Uint16Array;
  var i32 = Int32Array;
  var fleb = new u8([
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    1,
    1,
    1,
    1,
    2,
    2,
    2,
    2,
    3,
    3,
    3,
    3,
    4,
    4,
    4,
    4,
    5,
    5,
    5,
    5,
    0,
    /* unused */
    0,
    0,
    /* impossible */
    0
  ]);
  var fdeb = new u8([
    0,
    0,
    0,
    0,
    1,
    1,
    2,
    2,
    3,
    3,
    4,
    4,
    5,
    5,
    6,
    6,
    7,
    7,
    8,
    8,
    9,
    9,
    10,
    10,
    11,
    11,
    12,
    12,
    13,
    13,
    /* unused */
    0,
    0
  ]);
  var clim = new u8([16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]);
  var freb = function(eb, start) {
    var b3 = new u16(31);
    for (var i2 = 0; i2 < 31; ++i2) {
      b3[i2] = start += 1 << eb[i2 - 1];
    }
    var r2 = new i32(b3[30]);
    for (var i2 = 1; i2 < 30; ++i2) {
      for (var j2 = b3[i2]; j2 < b3[i2 + 1]; ++j2) {
        r2[j2] = j2 - b3[i2] << 5 | i2;
      }
    }
    return { b: b3, r: r2 };
  };
  var _a = freb(fleb, 2);
  var fl = _a.b;
  var revfl = _a.r;
  fl[28] = 258, revfl[258] = 28;
  var _b = freb(fdeb, 0);
  var fd = _b.b;
  var revfd = _b.r;
  var rev = new u16(32768);
  for (i = 0; i < 32768; ++i) {
    x = (i & 43690) >> 1 | (i & 21845) << 1;
    x = (x & 52428) >> 2 | (x & 13107) << 2;
    x = (x & 61680) >> 4 | (x & 3855) << 4;
    rev[i] = ((x & 65280) >> 8 | (x & 255) << 8) >> 1;
  }
  var x;
  var i;
  var hMap = (function(cd, mb, r2) {
    var s2 = cd.length;
    var i2 = 0;
    var l2 = new u16(mb);
    for (; i2 < s2; ++i2) {
      if (cd[i2])
        ++l2[cd[i2] - 1];
    }
    var le = new u16(mb);
    for (i2 = 1; i2 < mb; ++i2) {
      le[i2] = le[i2 - 1] + l2[i2 - 1] << 1;
    }
    var co;
    if (r2) {
      co = new u16(1 << mb);
      var rvb = 15 - mb;
      for (i2 = 0; i2 < s2; ++i2) {
        if (cd[i2]) {
          var sv = i2 << 4 | cd[i2];
          var r_1 = mb - cd[i2];
          var v2 = le[cd[i2] - 1]++ << r_1;
          for (var m2 = v2 | (1 << r_1) - 1; v2 <= m2; ++v2) {
            co[rev[v2] >> rvb] = sv;
          }
        }
      }
    } else {
      co = new u16(s2);
      for (i2 = 0; i2 < s2; ++i2) {
        if (cd[i2]) {
          co[i2] = rev[le[cd[i2] - 1]++] >> 15 - cd[i2];
        }
      }
    }
    return co;
  });
  var flt = new u8(288);
  for (i = 0; i < 144; ++i)
    flt[i] = 8;
  var i;
  for (i = 144; i < 256; ++i)
    flt[i] = 9;
  var i;
  for (i = 256; i < 280; ++i)
    flt[i] = 7;
  var i;
  for (i = 280; i < 288; ++i)
    flt[i] = 8;
  var i;
  var fdt = new u8(32);
  for (i = 0; i < 32; ++i)
    fdt[i] = 5;
  var i;
  var flrm = /* @__PURE__ */ hMap(flt, 9, 1);
  var fdrm = /* @__PURE__ */ hMap(fdt, 5, 1);
  var max = function(a) {
    var m2 = a[0];
    for (var i2 = 1; i2 < a.length; ++i2) {
      if (a[i2] > m2)
        m2 = a[i2];
    }
    return m2;
  };
  var bits = function(d3, p2, m2) {
    var o2 = p2 / 8 | 0;
    return (d3[o2] | d3[o2 + 1] << 8) >> (p2 & 7) & m2;
  };
  var bits16 = function(d3, p2) {
    var o2 = p2 / 8 | 0;
    return (d3[o2] | d3[o2 + 1] << 8 | d3[o2 + 2] << 16) >> (p2 & 7);
  };
  var shft = function(p2) {
    return (p2 + 7) / 8 | 0;
  };
  var slc = function(v2, s2, e) {
    if (s2 == null || s2 < 0)
      s2 = 0;
    if (e == null || e > v2.length)
      e = v2.length;
    return new u8(v2.subarray(s2, e));
  };
  var ec = [
    "unexpected EOF",
    "invalid block type",
    "invalid length/literal",
    "invalid distance",
    "stream finished",
    "no stream handler",
    ,
    // determined by compression function
    "no callback",
    "invalid UTF-8 data",
    "extra field too long",
    "date not in range 1980-2099",
    "filename too long",
    "stream finishing",
    "invalid zip data"
    // determined by unknown compression method
  ];
  var err = function(ind, msg, nt) {
    var e = new Error(msg || ec[ind]);
    e.code = ind;
    if (Error.captureStackTrace)
      Error.captureStackTrace(e, err);
    if (!nt)
      throw e;
    return e;
  };
  var inflt = function(dat, st, buf, dict) {
    var sl = dat.length, dl = dict ? dict.length : 0;
    if (!sl || st.f && !st.l)
      return buf || new u8(0);
    var noBuf = !buf;
    var resize = noBuf || st.i != 2;
    var noSt = st.i;
    if (noBuf)
      buf = new u8(sl * 3);
    var cbuf = function(l3) {
      var bl = buf.length;
      if (l3 > bl) {
        var nbuf = new u8(Math.max(bl * 2, l3));
        nbuf.set(buf);
        buf = nbuf;
      }
    };
    var final = st.f || 0, pos = st.p || 0, bt = st.b || 0, lm = st.l, dm = st.d, lbt = st.m, dbt = st.n;
    var tbts = sl * 8;
    do {
      if (!lm) {
        final = bits(dat, pos, 1);
        var type = bits(dat, pos + 1, 3);
        pos += 3;
        if (!type) {
          var s2 = shft(pos) + 4, l2 = dat[s2 - 4] | dat[s2 - 3] << 8, t = s2 + l2;
          if (t > sl) {
            if (noSt)
              err(0);
            break;
          }
          if (resize)
            cbuf(bt + l2);
          buf.set(dat.subarray(s2, t), bt);
          st.b = bt += l2, st.p = pos = t * 8, st.f = final;
          continue;
        } else if (type == 1)
          lm = flrm, dm = fdrm, lbt = 9, dbt = 5;
        else if (type == 2) {
          var hLit = bits(dat, pos, 31) + 257, hcLen = bits(dat, pos + 10, 15) + 4;
          var tl = hLit + bits(dat, pos + 5, 31) + 1;
          pos += 14;
          var ldt = new u8(tl);
          var clt = new u8(19);
          for (var i2 = 0; i2 < hcLen; ++i2) {
            clt[clim[i2]] = bits(dat, pos + i2 * 3, 7);
          }
          pos += hcLen * 3;
          var clb = max(clt), clbmsk = (1 << clb) - 1;
          var clm = hMap(clt, clb, 1);
          for (var i2 = 0; i2 < tl; ) {
            var r2 = clm[bits(dat, pos, clbmsk)];
            pos += r2 & 15;
            var s2 = r2 >> 4;
            if (s2 < 16) {
              ldt[i2++] = s2;
            } else {
              var c2 = 0, n = 0;
              if (s2 == 16)
                n = 3 + bits(dat, pos, 3), pos += 2, c2 = ldt[i2 - 1];
              else if (s2 == 17)
                n = 3 + bits(dat, pos, 7), pos += 3;
              else if (s2 == 18)
                n = 11 + bits(dat, pos, 127), pos += 7;
              while (n--)
                ldt[i2++] = c2;
            }
          }
          var lt = ldt.subarray(0, hLit), dt = ldt.subarray(hLit);
          lbt = max(lt);
          dbt = max(dt);
          lm = hMap(lt, lbt, 1);
          dm = hMap(dt, dbt, 1);
        } else
          err(1);
        if (pos > tbts) {
          if (noSt)
            err(0);
          break;
        }
      }
      if (resize)
        cbuf(bt + 131072);
      var lms = (1 << lbt) - 1, dms = (1 << dbt) - 1;
      var lpos = pos;
      for (; ; lpos = pos) {
        var c2 = lm[bits16(dat, pos) & lms], sym = c2 >> 4;
        pos += c2 & 15;
        if (pos > tbts) {
          if (noSt)
            err(0);
          break;
        }
        if (!c2)
          err(2);
        if (sym < 256)
          buf[bt++] = sym;
        else if (sym == 256) {
          lpos = pos, lm = null;
          break;
        } else {
          var add = sym - 254;
          if (sym > 264) {
            var i2 = sym - 257, b3 = fleb[i2];
            add = bits(dat, pos, (1 << b3) - 1) + fl[i2];
            pos += b3;
          }
          var d3 = dm[bits16(dat, pos) & dms], dsym = d3 >> 4;
          if (!d3)
            err(3);
          pos += d3 & 15;
          var dt = fd[dsym];
          if (dsym > 3) {
            var b3 = fdeb[dsym];
            dt += bits16(dat, pos) & (1 << b3) - 1, pos += b3;
          }
          if (pos > tbts) {
            if (noSt)
              err(0);
            break;
          }
          if (resize)
            cbuf(bt + 131072);
          var end = bt + add;
          if (bt < dt) {
            var shift = dl - dt, dend = Math.min(dt, end);
            if (shift + bt < 0)
              err(3);
            for (; bt < dend; ++bt)
              buf[bt] = dict[shift + bt];
          }
          for (; bt < end; ++bt)
            buf[bt] = buf[bt - dt];
        }
      }
      st.l = lm, st.p = lpos, st.b = bt, st.f = final;
      if (lm)
        final = 1, st.m = lbt, st.d = dm, st.n = dbt;
    } while (!final);
    return bt != buf.length && noBuf ? slc(buf, 0, bt) : buf.subarray(0, bt);
  };
  var et = /* @__PURE__ */ new u8(0);
  var gzs = function(d3) {
    if (d3[0] != 31 || d3[1] != 139 || d3[2] != 8)
      err(6, "invalid gzip data");
    var flg = d3[3];
    var st = 10;
    if (flg & 4)
      st += (d3[10] | d3[11] << 8) + 2;
    for (var zs = (flg >> 3 & 1) + (flg >> 4 & 1); zs > 0; zs -= !d3[st++])
      ;
    return st + (flg & 2);
  };
  var gzl = function(d3) {
    var l2 = d3.length;
    return (d3[l2 - 4] | d3[l2 - 3] << 8 | d3[l2 - 2] << 16 | d3[l2 - 1] << 24) >>> 0;
  };
  var zls = function(d3, dict) {
    if ((d3[0] & 15) != 8 || d3[0] >> 4 > 7 || (d3[0] << 8 | d3[1]) % 31)
      err(6, "invalid zlib data");
    if ((d3[1] >> 5 & 1) == +!dict)
      err(6, "invalid zlib data: " + (d3[1] & 32 ? "need" : "unexpected") + " dictionary");
    return (d3[1] >> 3 & 4) + 2;
  };
  function inflateSync(data, opts) {
    return inflt(data, { i: 2 }, opts && opts.out, opts && opts.dictionary);
  }
  function gunzipSync(data, opts) {
    var st = gzs(data);
    if (st + 8 > data.length)
      err(6, "invalid gzip data");
    return inflt(data.subarray(st, -8), { i: 2 }, opts && opts.out || new u8(gzl(data)), opts && opts.dictionary);
  }
  function unzlibSync(data, opts) {
    return inflt(data.subarray(zls(data, opts && opts.dictionary), -4), { i: 2 }, opts && opts.out, opts && opts.dictionary);
  }
  function decompressSync(data, opts) {
    return data[0] == 31 && data[1] == 139 && data[2] == 8 ? gunzipSync(data, opts) : (data[0] & 15) != 8 || data[0] >> 4 > 7 || (data[0] << 8 | data[1]) % 31 ? inflateSync(data, opts) : unzlibSync(data, opts);
  }
  var td = typeof TextDecoder != "undefined" && /* @__PURE__ */ new TextDecoder();
  var tds = 0;
  try {
    td.decode(et, { stream: true });
    tds = 1;
  } catch (e) {
  }

  // .tools/jsdeps/node_modules/pmtiles/dist/esm/index.js
  var j = Object.defineProperty;
  var S = Math.pow;
  var d = (o2, t) => j(o2, "name", { value: t, configurable: true });
  var h = (o2, t, e) => new Promise((r2, n) => {
    var s2 = (c2) => {
      try {
        a(e.next(c2));
      } catch (l2) {
        n(l2);
      }
    }, i2 = (c2) => {
      try {
        a(e.throw(c2));
      } catch (l2) {
        n(l2);
      }
    }, a = (c2) => c2.done ? r2(c2.value) : Promise.resolve(c2.value).then(s2, i2);
    a((e = e.apply(o2, t)).next());
  });
  var re = d((o2, t) => {
    let e = false, r2 = "", n = L.GridLayer.extend({ createTile: d((s2, i2) => {
      let a = document.createElement("img"), c2 = new AbortController(), l2 = c2.signal;
      return a.cancel = () => {
        c2.abort();
      }, e || (o2.getHeader().then((u2) => {
        u2.tileType === 1 || u2.tileType === 6 ? console.error("Error: archive contains vector tiles, but leafletRasterLayer is for displaying raster tiles. See https://github.com/protomaps/PMTiles/tree/main/js for details.") : u2.tileType === 2 ? r2 = "image/png" : u2.tileType === 3 ? r2 = "image/jpeg" : u2.tileType === 4 ? r2 = "image/webp" : u2.tileType === 5 && (r2 = "image/avif");
      }), e = true), o2.getZxy(s2.z, s2.x, s2.y, l2).then((u2) => {
        if (u2) {
          let m2 = new Blob([u2.data], { type: r2 }), g2 = window.URL.createObjectURL(m2);
          a.src = g2;
        } else a.style.display = "none";
        a.cancel = void 0, i2(void 0, a);
      }).catch((u2) => {
        if (u2.name !== "AbortError") throw u2;
      }), a;
    }, "createTile"), _removeTile: d(function(s2) {
      let i2 = this._tiles[s2];
      i2 && (i2.el.cancel && i2.el.cancel(), i2.el.src && window.URL.revokeObjectURL(i2.el.src), i2.el.width = 0, i2.el.height = 0, i2.el.deleted = true, L.DomUtil.remove(i2.el), delete this._tiles[s2], this.fire("tileunload", { tile: i2.el, coords: this._keyToTileCoords(s2) }));
    }, "_removeTile") });
    return new n(t);
  }, "leafletRasterLayer");
  var z = d((o2) => (t, e) => {
    if (e instanceof AbortController) return o2(t, e);
    let r2 = new AbortController();
    return o2(t, r2).then((n) => e(void 0, n.data, n.cacheControl || "", n.expires || ""), (n) => e(n)).catch((n) => e(n)), { cancel: d(() => r2.abort(), "cancel") };
  }, "v3compat");
  var A = class A2 {
    constructor(t) {
      this.tilev4 = d((t2, e) => h(this, null, function* () {
        if (t2.type === "json") {
          let g2 = t2.url.substr(10), p2 = this.tiles.get(g2);
          if (p2 || (p2 = new w(g2), this.tiles.set(g2, p2)), this.metadata) {
            let K = yield p2.getTileJson(t2.url);
            return e.signal.throwIfAborted(), { data: K };
          }
          let f2 = yield p2.getHeader();
          return e.signal.throwIfAborted(), (f2.minLon >= f2.maxLon || f2.minLat >= f2.maxLat) && console.error(`Bounds of PMTiles archive ${f2.minLon},${f2.minLat},${f2.maxLon},${f2.maxLat} are not valid.`), { data: { tiles: [`${t2.url}/{z}/{x}/{y}`], minzoom: f2.minZoom, maxzoom: f2.maxZoom, bounds: [f2.minLon, f2.minLat, f2.maxLon, f2.maxLat] } };
        }
        let r2 = new RegExp(/pmtiles:\/\/(.+)\/(\d+)\/(\d+)\/(\d+)/), n = t2.url.match(r2);
        if (!n) throw new Error("Invalid PMTiles protocol URL");
        let s2 = n[1], i2 = this.tiles.get(s2);
        i2 || (i2 = new w(s2), this.tiles.set(s2, i2));
        let a = n[2], c2 = n[3], l2 = n[4], u2 = yield i2 == null ? void 0 : i2.getZxy(+a, +c2, +l2, e.signal);
        if (e.signal.throwIfAborted(), u2) return { data: new Uint8Array(u2.data), cacheControl: u2.cacheControl, expires: u2.expires };
        let m2 = yield i2.getHeader();
        if (m2.tileType === 1 || m2.tileType === 6) {
          if (this.errorOnMissingTile) throw new Error("Tile not found.");
          return { data: new Uint8Array() };
        }
        return { data: null };
      }), "tilev4");
      this.tile = z(this.tilev4);
      this.tiles = /* @__PURE__ */ new Map(), this.metadata = (t == null ? void 0 : t.metadata) || false, this.errorOnMissingTile = (t == null ? void 0 : t.errorOnMissingTile) || false;
    }
    add(t) {
      this.tiles.set(t.source.getKey(), t);
    }
    get(t) {
      return this.tiles.get(t);
    }
  };
  d(A, "Protocol");
  var B = A;
  function b(o2, t) {
    return (t >>> 0) * 4294967296 + (o2 >>> 0);
  }
  d(b, "toNum");
  function N(o2, t) {
    let e = t.buf, r2 = e[t.pos++], n = (r2 & 112) >> 4;
    if (r2 < 128 || (r2 = e[t.pos++], n |= (r2 & 127) << 3, r2 < 128) || (r2 = e[t.pos++], n |= (r2 & 127) << 10, r2 < 128) || (r2 = e[t.pos++], n |= (r2 & 127) << 17, r2 < 128) || (r2 = e[t.pos++], n |= (r2 & 127) << 24, r2 < 128) || (r2 = e[t.pos++], n |= (r2 & 1) << 31, r2 < 128)) return b(o2, n);
    throw new Error("Expected varint not more than 10 bytes");
  }
  d(N, "readVarintRemainder");
  function x2(o2) {
    let t = o2.buf, e = t[o2.pos++], r2 = e & 127;
    return e < 128 || (e = t[o2.pos++], r2 |= (e & 127) << 7, e < 128) || (e = t[o2.pos++], r2 |= (e & 127) << 14, e < 128) || (e = t[o2.pos++], r2 |= (e & 127) << 21, e < 128) ? r2 : (e = t[o2.pos], r2 |= (e & 15) << 28, N(r2, o2));
  }
  d(x2, "readVarint");
  function I(o2, t, e, r2, n) {
    return n === 0 ? r2 !== 0 ? [o2 - 1 - e, o2 - 1 - t] : [e, t] : [t, e];
  }
  d(I, "rotate");
  function q(o2, t, e) {
    if (o2 > 26) throw new Error("Tile zoom level exceeds max safe number limit (26)");
    if (t >= 1 << o2 || e >= 1 << o2) throw new Error("tile x/y outside zoom level bounds");
    let r2 = ((1 << o2) * (1 << o2) - 1) / 3, n = o2 - 1, [s2, i2] = [t, e];
    for (let a = 1 << n; a > 0; a >>= 1) {
      let c2 = s2 & a, l2 = i2 & a;
      r2 += (3 * c2 ^ l2) * (1 << n), [s2, i2] = I(a, s2, i2, c2, l2), n--;
    }
    return r2;
  }
  d(q, "zxyToTileId");
  function G(o2) {
    let t = 3 * o2 + 1;
    return t < 4294967296 ? 31 - Math.clz32(t) : 63 - Math.clz32(t / 4294967296);
  }
  d(G, "tileIdToZ");
  function ie(o2) {
    let t = G(o2) >> 1;
    if (t > 26) throw new Error("Tile zoom level exceeds max safe number limit (26)");
    let e = ((1 << t) * (1 << t) - 1) / 3, r2 = o2 - e, n = 0, s2 = 0, i2 = 1 << t;
    for (let a = 1; a < i2; a <<= 1) {
      let c2 = a & r2 / 2, l2 = a & (r2 ^ c2);
      [n, s2] = I(a, n, s2, c2, l2), r2 = r2 / 2, n += c2, s2 += l2;
    }
    return [t, n, s2];
  }
  d(ie, "tileIdToZxy");
  var J = ((s2) => (s2[s2.Unknown = 0] = "Unknown", s2[s2.None = 1] = "None", s2[s2.Gzip = 2] = "Gzip", s2[s2.Brotli = 3] = "Brotli", s2[s2.Zstd = 4] = "Zstd", s2))(J || {});
  function P(o2, t) {
    return h(this, null, function* () {
      if (t === 1 || t === 0) return o2;
      if (t === 2) {
        if (typeof globalThis.DecompressionStream == "undefined") return decompressSync(new Uint8Array(o2));
        let e = new Response(o2).body;
        if (!e) throw new Error("Failed to read response stream");
        let r2 = e.pipeThrough(new globalThis.DecompressionStream("gzip"));
        return new Response(r2).arrayBuffer();
      }
      throw new Error("Compression method not supported");
    });
  }
  d(P, "defaultDecompress");
  var O = ((a) => (a[a.Unknown = 0] = "Unknown", a[a.Mvt = 1] = "Mvt", a[a.Png = 2] = "Png", a[a.Jpeg = 3] = "Jpeg", a[a.Webp = 4] = "Webp", a[a.Avif = 5] = "Avif", a[a.Mlt = 6] = "Mlt", a))(O || {});
  function _(o2) {
    return o2 === 1 ? ".mvt" : o2 === 2 ? ".png" : o2 === 3 ? ".jpg" : o2 === 4 ? ".webp" : o2 === 5 ? ".avif" : o2 === 6 ? ".mlt" : "";
  }
  d(_, "tileTypeExt");
  var Y = 127;
  function Q(o2, t) {
    let e = 0, r2 = o2.length - 1;
    for (; e <= r2; ) {
      let n = r2 + e >> 1, s2 = t - o2[n].tileId;
      if (s2 > 0) e = n + 1;
      else if (s2 < 0) r2 = n - 1;
      else return o2[n];
    }
    return r2 >= 0 && (o2[r2].runLength === 0 || t - o2[r2].tileId < o2[r2].runLength) ? o2[r2] : null;
  }
  d(Q, "findTile");
  var T = class T2 {
    constructor(t) {
      this.file = t;
    }
    getKey() {
      return this.file.name;
    }
    getBytes(t, e) {
      return h(this, null, function* () {
        return { data: yield this.file.slice(t, t + e).arrayBuffer() };
      });
    }
  };
  d(T, "FileSource");
  var k = T;
  var D = class D2 {
    constructor(t, e = new Headers(), r2 = void 0) {
      var a, c2;
      this.url = t, this.customHeaders = e, this.credentials = r2, this.mustReload = false;
      let n = "";
      "navigator" in globalThis && (n = (c2 = (a = globalThis.navigator) == null ? void 0 : a.userAgent) != null ? c2 : "");
      let s2 = n.indexOf("Windows") > -1, i2 = /Chrome|Chromium|Edg|OPR|Brave/.test(n);
      this.chromeWindowsNoCache = false, s2 && i2 && (this.chromeWindowsNoCache = true);
    }
    getKey() {
      return this.url;
    }
    setHeaders(t) {
      this.customHeaders = t;
    }
    getBytes(t, e, r2, n) {
      return h(this, null, function* () {
        let s2, i2;
        r2 ? i2 = r2 : (s2 = new AbortController(), i2 = s2.signal);
        let a = new Headers(this.customHeaders);
        a.set("range", `bytes=${t}-${t + e - 1}`);
        let c2;
        this.mustReload ? c2 = "reload" : this.chromeWindowsNoCache && (c2 = "no-store");
        let l2 = yield fetch(this.url, { signal: i2, cache: c2, headers: a, credentials: this.credentials });
        if (t === 0 && l2.status === 416) {
          let p2 = l2.headers.get("Content-Range");
          if (!p2 || !p2.startsWith("bytes */")) throw new Error("Missing content-length on 416 response");
          let f2 = +p2.substr(8);
          a.set("range", `bytes=0-${f2 - 1}`), l2 = yield fetch(this.url, { signal: i2, cache: "reload", headers: a, credentials: this.credentials });
        }
        let u2 = l2.headers.get("Etag");
        if (u2 != null && u2.startsWith("W/") && (u2 = null), l2.status === 416 || n && u2 && u2 !== n) throw this.mustReload = true, new v(`Server returned non-matching ETag ${n} after one retry. Check browser extensions and servers for issues that may affect correct ETag headers.`);
        if (l2.status >= 300) throw new Error(`Bad response code: ${l2.status}`);
        let m2 = l2.headers.get("Content-Length");
        if (l2.status === 200 && (!m2 || +m2 > e)) throw s2 && s2.abort(), new Error("Server returned no content-length header or content-length exceeding request. Check that your storage backend supports HTTP Byte Serving.");
        return { data: yield l2.arrayBuffer(), etag: u2 || void 0, cacheControl: l2.headers.get("Cache-Control") || void 0, expires: l2.headers.get("Expires") || void 0 };
      });
    }
  };
  d(D, "FetchSource");
  var E = D;
  function y(o2, t) {
    let e = o2.getUint32(t + 4, true), r2 = o2.getUint32(t + 0, true);
    return e * S(2, 32) + r2;
  }
  d(y, "getUint64");
  function X(o2, t) {
    let e = new DataView(o2), r2 = e.getUint8(7);
    if (r2 > 3) throw new Error(`Archive is spec version ${r2} but this library supports up to spec version 3`);
    return { specVersion: r2, rootDirectoryOffset: y(e, 8), rootDirectoryLength: y(e, 16), jsonMetadataOffset: y(e, 24), jsonMetadataLength: y(e, 32), leafDirectoryOffset: y(e, 40), leafDirectoryLength: y(e, 48), tileDataOffset: y(e, 56), tileDataLength: y(e, 64), numAddressedTiles: y(e, 72), numTileEntries: y(e, 80), numTileContents: y(e, 88), clustered: e.getUint8(96) === 1, internalCompression: e.getUint8(97), tileCompression: e.getUint8(98), tileType: e.getUint8(99), minZoom: e.getUint8(100), maxZoom: e.getUint8(101), minLon: e.getInt32(102, true) / 1e7, minLat: e.getInt32(106, true) / 1e7, maxLon: e.getInt32(110, true) / 1e7, maxLat: e.getInt32(114, true) / 1e7, centerZoom: e.getUint8(118), centerLon: e.getInt32(119, true) / 1e7, centerLat: e.getInt32(123, true) / 1e7, etag: t };
  }
  d(X, "bytesToHeader");
  function Z(o2) {
    let t = { buf: new Uint8Array(o2), pos: 0 }, e = x2(t), r2 = [], n = 0;
    for (let s2 = 0; s2 < e; s2++) {
      let i2 = x2(t);
      r2.push({ tileId: n + i2, offset: 0, length: 0, runLength: 1 }), n += i2;
    }
    for (let s2 = 0; s2 < e; s2++) r2[s2].runLength = x2(t);
    for (let s2 = 0; s2 < e; s2++) r2[s2].length = x2(t);
    for (let s2 = 0; s2 < e; s2++) {
      let i2 = x2(t);
      i2 === 0 && s2 > 0 ? r2[s2].offset = r2[s2 - 1].offset + r2[s2 - 1].length : r2[s2].offset = i2 - 1;
    }
    return r2;
  }
  d(Z, "deserializeIndex");
  var R = class R2 extends Error {
  };
  d(R, "EtagMismatch");
  var v = R;
  function V(o2, t) {
    return h(this, null, function* () {
      let e = yield o2.getBytes(0, 16384);
      if (new DataView(e.data).getUint16(0, true) !== 19792) throw new Error("Wrong magic number for PMTiles archive");
      let n = e.data.slice(0, Y), s2 = X(n, e.etag), i2 = e.data.slice(s2.rootDirectoryOffset, s2.rootDirectoryOffset + s2.rootDirectoryLength), a = `${o2.getKey()}|${s2.etag || ""}|${s2.rootDirectoryOffset}|${s2.rootDirectoryLength}`, c2 = Z(yield t(i2, s2.internalCompression));
      return [s2, [a, c2.length, c2]];
    });
  }
  d(V, "getHeaderAndRoot");
  function F(o2, t, e, r2, n, s2) {
    return h(this, null, function* () {
      let i2 = yield o2.getBytes(e, r2, s2, n.etag), a = yield t(i2.data, n.internalCompression), c2 = Z(a);
      if (c2.length === 0) throw new Error("Empty directory is invalid");
      return c2;
    });
  }
  d(F, "getDirectory");
  var U = class U2 {
    constructor(t = 100, e = true, r2 = P) {
      this.cache = /* @__PURE__ */ new Map(), this.maxCacheEntries = t, this.counter = 1, this.decompress = r2;
    }
    getHeader(t) {
      return h(this, null, function* () {
        let e = t.getKey(), r2 = this.cache.get(e);
        if (r2) return r2.lastUsed = this.counter++, r2.data;
        let n = yield V(t, this.decompress);
        return n[1] && this.cache.set(n[1][0], { lastUsed: this.counter++, data: n[1][2] }), this.cache.set(e, { lastUsed: this.counter++, data: n[0] }), this.prune(), n[0];
      });
    }
    getDirectory(t, e, r2, n, s2) {
      return h(this, null, function* () {
        let i2 = `${t.getKey()}|${n.etag || ""}|${e}|${r2}`, a = this.cache.get(i2);
        if (a) return a.lastUsed = this.counter++, a.data;
        let c2 = yield F(t, this.decompress, e, r2, n, s2);
        return this.cache.set(i2, { lastUsed: this.counter++, data: c2 }), this.prune(), c2;
      });
    }
    prune() {
      if (this.cache.size > this.maxCacheEntries) {
        let t = 1 / 0, e;
        this.cache.forEach((r2, n) => {
          r2.lastUsed < t && (t = r2.lastUsed, e = n);
        }), e && this.cache.delete(e);
      }
    }
    invalidate(t) {
      return h(this, null, function* () {
        this.cache.delete(t.getKey());
      });
    }
  };
  d(U, "ResolvedValueCache");
  var M = class M2 {
    constructor(t = 100, e = true, r2 = P) {
      this.cache = /* @__PURE__ */ new Map(), this.invalidations = /* @__PURE__ */ new Map(), this.pendingFetches = /* @__PURE__ */ new Map(), this.maxCacheEntries = t, this.counter = 1, this.decompress = r2;
    }
    getHeader(t) {
      return h(this, null, function* () {
        let e = t.getKey(), r2 = this.cache.get(e);
        if (r2) return r2.lastUsed = this.counter++, yield r2.data;
        let n = new Promise((s2, i2) => {
          V(t, this.decompress).then((a) => {
            a[1] && this.cache.set(a[1][0], { lastUsed: this.counter++, data: Promise.resolve(a[1][2]) }), s2(a[0]), this.prune();
          }).catch((a) => {
            i2(a);
          });
        });
        return this.cache.set(e, { lastUsed: this.counter++, data: n }), n;
      });
    }
    trackSignal(t, e, r2) {
      e.refs++, r2.addEventListener("abort", () => {
        --e.refs <= 0 && this.pendingFetches.get(t) === e && (e.controller.abort(), this.cache.delete(t), this.pendingFetches.delete(t));
      }, { once: true });
    }
    getDirectory(t, e, r2, n, s2) {
      return h(this, null, function* () {
        let i2 = `${t.getKey()}|${n.etag || ""}|${e}|${r2}`, a = this.cache.get(i2);
        if (a) {
          a.lastUsed = this.counter++;
          let m2 = this.pendingFetches.get(i2);
          return m2 && this.trackSignal(i2, m2, s2 != null ? s2 : new AbortController().signal), yield a.data;
        }
        let c2 = new AbortController(), l2 = { controller: c2, refs: 0 };
        this.trackSignal(i2, l2, s2 != null ? s2 : new AbortController().signal), this.pendingFetches.set(i2, l2);
        let u2 = new Promise((m2, g2) => {
          F(t, this.decompress, e, r2, n, c2.signal).then((p2) => {
            this.pendingFetches.delete(i2), m2(p2), this.prune();
          }).catch((p2) => {
            g2(p2);
          });
        });
        return this.cache.set(i2, { lastUsed: this.counter++, data: u2 }), u2;
      });
    }
    prune() {
      if (this.cache.size >= this.maxCacheEntries) {
        let t = 1 / 0, e;
        this.cache.forEach((r2, n) => {
          r2.lastUsed < t && (t = r2.lastUsed, e = n);
        }), e && this.cache.delete(e);
      }
    }
    invalidate(t) {
      return h(this, null, function* () {
        let e = t.getKey();
        if (this.invalidations.get(e)) return yield this.invalidations.get(e);
        this.cache.delete(t.getKey());
        let r2 = new Promise((n, s2) => {
          this.getHeader(t).then((i2) => {
            n(), this.invalidations.delete(e);
          }).catch((i2) => {
            s2(i2);
          });
        });
        this.invalidations.set(e, r2);
      });
    }
  };
  d(M, "SharedPromiseCache");
  var C = M;
  var H = class H2 {
    constructor(t, e, r2) {
      typeof t == "string" ? this.source = new E(t) : this.source = t, r2 ? this.decompress = r2 : this.decompress = P, e ? this.cache = e : this.cache = new C();
    }
    getHeader() {
      return h(this, null, function* () {
        return yield this.cache.getHeader(this.source);
      });
    }
    getZxyAttempt(t, e, r2, n) {
      return h(this, null, function* () {
        let s2 = q(t, e, r2), i2 = yield this.cache.getHeader(this.source);
        if (n == null || n.throwIfAborted(), t < i2.minZoom || t > i2.maxZoom) return;
        let a = i2.rootDirectoryOffset, c2 = i2.rootDirectoryLength;
        for (let l2 = 0; l2 <= 3; l2++) {
          let u2 = yield this.cache.getDirectory(this.source, a, c2, i2, n);
          n == null || n.throwIfAborted();
          let m2 = Q(u2, s2);
          if (m2) {
            if (m2.runLength > 0) {
              let g2 = yield this.source.getBytes(i2.tileDataOffset + m2.offset, m2.length, n, i2.etag);
              return { data: yield this.decompress(g2.data, i2.tileCompression), cacheControl: g2.cacheControl, expires: g2.expires };
            }
            a = i2.leafDirectoryOffset + m2.offset, c2 = m2.length;
          } else return;
        }
        throw new Error("Maximum directory depth exceeded");
      });
    }
    getZxy(t, e, r2, n) {
      return h(this, null, function* () {
        try {
          return yield this.getZxyAttempt(t, e, r2, n);
        } catch (s2) {
          if (s2 instanceof v) return this.cache.invalidate(this.source), yield this.getZxyAttempt(t, e, r2, n);
          throw s2;
        }
      });
    }
    getMetadataAttempt() {
      return h(this, null, function* () {
        let t = yield this.cache.getHeader(this.source), e = yield this.source.getBytes(t.jsonMetadataOffset, t.jsonMetadataLength, void 0, t.etag), r2 = yield this.decompress(e.data, t.internalCompression), n = new TextDecoder("utf-8");
        return JSON.parse(n.decode(r2));
      });
    }
    getMetadata() {
      return h(this, null, function* () {
        try {
          return yield this.getMetadataAttempt();
        } catch (t) {
          if (t instanceof v) return this.cache.invalidate(this.source), yield this.getMetadataAttempt();
          throw t;
        }
      });
    }
    getTileJson(t) {
      return h(this, null, function* () {
        let e = yield this.getHeader(), r2 = yield this.getMetadata(), n = _(e.tileType);
        return { tilejson: "3.0.0", scheme: "xyz", tiles: [`${t}/{z}/{x}/{y}${n}`], vector_layers: r2.vector_layers, attribution: r2.attribution, description: r2.description, name: r2.name, version: r2.version, bounds: [e.minLon, e.minLat, e.maxLon, e.maxLat], center: [e.centerLon, e.centerLat, e.centerZoom], minzoom: e.minZoom, maxzoom: e.maxZoom };
      });
    }
  };
  d(H, "PMTiles");
  var w = H;

  // .tools/jsdeps/node_modules/@protomaps/basemaps/dist/esm/index.js
  var k2 = Object.defineProperty;
  var r = (a, e) => k2(a, "name", { value: e, configurable: true });
  function l(a, e) {
    let n = "script";
    return a === "name" ? n = "script" : a === "name2" ? n = "script2" : a === "name3" && (n = "script3"), [["coalesce", ["get", `pgf:${a}`], ["get", a]], { "text-font": ["case", ["==", ["get", n], "Devanagari"], ["literal", ["Noto Sans Devanagari Regular v1"]], ["literal", [e || "Noto Sans Regular"]]] }];
  }
  r(l, "get_name_block");
  function c(a, e, n) {
    let i2 = "name";
    return n === "name" ? i2 = "" : n === "name2" ? i2 = "2" : n === "name3" && (i2 = "3"), e === "Latin" ? ["has", `script${i2}`] : a === "ja" ? ["all", ["!=", ["get", `script${i2}`], "Han"], ["!=", ["get", `script${i2}`], "Hiragana"], ["!=", ["get", `script${i2}`], "Katakana"], ["!=", ["get", `script${i2}`], "Mixed-Japanese"]] : ["!=", ["get", `script${i2}`], e];
  }
  r(c, "is_not_in_target_script");
  function s(a) {
    return a === "Devanagari" ? { "text-font": ["literal", ["Noto Sans Devanagari Regular v1"]] } : {};
  }
  r(s, "get_font_formatting");
  function _2(a) {
    let e = g.find((n) => n.lang === a);
    return e === void 0 ? "Latin" : e.script;
  }
  r(_2, "get_default_script");
  function d2(a, e) {
    let n = e || _2(a), i2;
    return n === "Devanagari" ? i2 = "pgf:" : i2 = "", ["format", ["coalesce", ["get", `${i2}name:${a}`], ["get", "name:en"]], s(n)];
  }
  r(d2, "get_country_name");
  function o(a, e, n) {
    let i2 = e || _2(a), t;
    return i2 === "Devanagari" ? t = "pgf:" : t = "", ["case", ["all", ["any", ["has", "name"], ["has", "pgf:name"]], ["!", ["any", ["has", "name2"], ["has", "pgf:name2"]]], ["!", ["any", ["has", "name3"], ["has", "pgf:name3"]]]], ["case", c(a, i2, "name"), ["case", ["any", ["is-supported-script", ["get", "name"]], ["has", "pgf:name"]], ["format", ["coalesce", ["get", `${t}name:${a}`], ["get", "name:en"]], s(i2), `
`, {}, ["case", ["all", ["!", ["has", `${t}name:${a}`]], ["has", "name:en"], ["!", ["has", "script"]]], "", ["coalesce", ["get", "pgf:name"], ["get", "name"]]], { "text-font": ["case", ["==", ["get", "script"], "Devanagari"], ["literal", ["Noto Sans Devanagari Regular v1"]], ["literal", [n || "Noto Sans Regular"]]] }], ["get", "name:en"]], ["format", ["coalesce", ["get", `${t}name:${a}`], ["get", "pgf:name"], ["get", "name"]], s(i2)]], ["all", ["any", ["has", "name"], ["has", "pgf:name"]], ["any", ["has", "name2"], ["has", "pgf:name2"]], ["!", ["any", ["has", "name3"], ["has", "pgf:name3"]]]], ["case", ["all", c(a, i2, "name"), c(a, i2, "name2")], ["format", ["get", `${t}name:${a}`], s(i2), `
`, {}, ...l("name", n), `
`, {}, ...l("name2", n)], ["case", c(a, i2, "name2"), ["format", ["coalesce", ["get", `${t}name:${a}`], ["get", "pgf:name"], ["get", "name"]], s(i2), `
`, {}, ...l("name2", n)], ["format", ["coalesce", ["get", `${t}name:${a}`], ["get", "pgf:name2"], ["get", "name2"]], s(i2), `
`, {}, ...l("name", n)]]], ["case", ["all", c(a, i2, "name"), c(a, i2, "name2"), c(a, i2, "name3")], ["format", ["get", `${t}name:${a}`], s(i2), `
`, {}, ...l("name", n), `
`, {}, ...l("name2", n), `
`, {}, ...l("name3", n)], ["case", ["!", c(a, i2, "name")], ["format", ["coalesce", ["get", `${t}name:${a}`], ["get", "pgf:name"], ["get", "name"]], s(i2), `
`, {}, ...l("name2", n), `
`, {}, ...l("name3", n)], ["!", c(a, i2, "name2")], ["format", ["coalesce", ["get", `${t}name:${a}`], ["get", "pgf:name2"], ["get", "name2"]], s(i2), `
`, {}, ...l("name", n), `
`, {}, ...l("name3", n)], ["format", ["coalesce", ["get", `${t}name:${a}`], ["get", "pgf:name3"], ["get", "name3"]], s(i2), `
`, {}, ...l("name", n), `
`, {}, ...l("name2", n)]]]];
  }
  r(o, "get_multiline_name");
  var g = [{ lang: "ar", full_name: "Arabic", script: "Arabic" }, { lang: "cs", full_name: "Czech", script: "Latin" }, { lang: "bg", full_name: "Bulgarian", script: "Cyrillic" }, { lang: "da", full_name: "Danish", script: "Latin" }, { lang: "de", full_name: "German", script: "Latin" }, { lang: "el", full_name: "Greek", script: "Greek" }, { lang: "en", full_name: "English", script: "Latin" }, { lang: "es", full_name: "Spanish", script: "Latin" }, { lang: "et", full_name: "Estonian", script: "Latin" }, { lang: "fa", full_name: "Persian", script: "Arabic" }, { lang: "fi", full_name: "Finnish", script: "Latin" }, { lang: "fr", full_name: "French", script: "Latin" }, { lang: "ga", full_name: "Irish", script: "Latin" }, { lang: "he", full_name: "Hebrew", script: "Hebrew" }, { lang: "hi", full_name: "Hindi", script: "Devanagari" }, { lang: "hr", full_name: "Croatian", script: "Latin" }, { lang: "hu", full_name: "Hungarian", script: "Latin" }, { lang: "id", full_name: "Indonesian", script: "Latin" }, { lang: "it", full_name: "Italian", script: "Latin" }, { lang: "ja", full_name: "Japanese", script: "" }, { lang: "ko", full_name: "Korean", script: "Hangul" }, { lang: "lt", full_name: "Lithuanian", script: "Latin" }, { lang: "lv", full_name: "Latvian", script: "Latin" }, { lang: "ne", full_name: "Nepali", script: "Devanagari" }, { lang: "nl", full_name: "Dutch", script: "Latin" }, { lang: "no", full_name: "Norwegian", script: "Latin" }, { lang: "mr", full_name: "Marathi", script: "Devanagari" }, { lang: "mt", full_name: "Maltese", script: "Latin" }, { lang: "pl", full_name: "Polish", script: "Latin" }, { lang: "pt", full_name: "Portuguese", script: "Latin" }, { lang: "ro", full_name: "Romanian", script: "Latin" }, { lang: "ru", full_name: "Russian", script: "Cyrillic" }, { lang: "sk", full_name: "Slovak", script: "Latin" }, { lang: "sl", full_name: "Slovenian", script: "Latin" }, { lang: "sv", full_name: "Swedish", script: "Latin" }, { lang: "tr", full_name: "Turkish", script: "Latin" }, { lang: "uk", full_name: "Ukrainian", script: "Cyrillic" }, { lang: "ur", full_name: "Urdu", script: "Arabic" }, { lang: "vi", full_name: "Vietnamese", script: "Latin" }, { lang: "zh-Hans", full_name: "Chinese (Simplified)", script: "Han" }, { lang: "zh-Hant", full_name: "Chinese (Traditional)", script: "Han" }];
  function f(a, e) {
    return [{ id: "background", type: "background", paint: { "background-color": e.background } }, { id: "earth", type: "fill", filter: ["==", "$type", "Polygon"], source: a, "source-layer": "earth", paint: { "fill-color": e.earth } }, ...e.landcover ? [{ id: "landcover", type: "fill", source: a, "source-layer": "landcover", paint: { "fill-color": ["match", ["get", "kind"], "grassland", e.landcover.grassland, "barren", e.landcover.barren, "urban_area", e.landcover.urban_area, "farmland", e.landcover.farmland, "glacier", e.landcover.glacier, "scrub", e.landcover.scrub, e.landcover.forest], "fill-opacity": ["interpolate", ["linear"], ["zoom"], 5, 1, 7, 0] } }] : [], { id: "landuse_park", type: "fill", source: a, "source-layer": "landuse", filter: ["in", "kind", "national_park", "park", "cemetery", "protected_area", "nature_reserve", "forest", "golf_course", "wood", "scrub", "grassland", "grass", "glacier", "sand", "military", "naval_base", "airfield"], paint: { "fill-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0, 11, 1], "fill-color": ["case", ["in", ["get", "kind"], ["literal", ["national_park", "park", "cemetery", "protected_area", "nature_reserve", "forest", "golf_course"]]], e.park_b, ["==", ["get", "kind"], "wood"], e.wood_b, ["in", ["get", "kind"], ["literal", ["scrub", "grassland", "grass"]]], e.scrub_b, ["==", ["get", "kind"], "glacier"], e.glacier, ["==", ["get", "kind"], "sand"], e.sand, ["in", ["get", "kind"], ["literal", ["military", "naval_base", "airfield"]]], e.zoo, e.earth] } }, { id: "landuse_urban_green", type: "fill", source: a, "source-layer": "landuse", filter: ["in", "kind", "allotments", "village_green", "playground"], paint: { "fill-color": e.park_b, "fill-opacity": 0.7 } }, { id: "landuse_hospital", type: "fill", source: a, "source-layer": "landuse", filter: ["==", "kind", "hospital"], paint: { "fill-color": e.hospital } }, { id: "landuse_industrial", type: "fill", source: a, "source-layer": "landuse", filter: ["==", "kind", "industrial"], paint: { "fill-color": e.industrial } }, { id: "landuse_school", type: "fill", source: a, "source-layer": "landuse", filter: ["in", "kind", "school", "university", "college"], paint: { "fill-color": e.school } }, { id: "landuse_beach", type: "fill", source: a, "source-layer": "landuse", filter: ["in", "kind", "beach"], paint: { "fill-color": e.beach } }, { id: "landuse_zoo", type: "fill", source: a, "source-layer": "landuse", filter: ["in", "kind", "zoo"], paint: { "fill-color": e.zoo } }, { id: "landuse_aerodrome", type: "fill", source: a, "source-layer": "landuse", filter: ["in", "kind", "aerodrome"], paint: { "fill-color": e.aerodrome } }, { id: "roads_runway", type: "line", source: a, "source-layer": "roads", filter: ["==", "kind_detail", "runway"], paint: { "line-color": e.runway, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 10, 0, 12, 4, 18, 30] } }, { id: "roads_taxiway", type: "line", source: a, "source-layer": "roads", minzoom: 13, filter: ["==", "kind_detail", "taxiway"], paint: { "line-color": e.runway, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1, 15, 6] } }, { id: "landuse_runway", type: "fill", source: a, "source-layer": "landuse", filter: ["any", ["in", "kind", "runway", "taxiway"]], paint: { "fill-color": e.runway } }, { id: "water", type: "fill", filter: ["==", "$type", "Polygon"], source: a, "source-layer": "water", paint: { "fill-color": e.water } }, { id: "water_stream", type: "line", source: a, "source-layer": "water", minzoom: 14, filter: ["in", "kind", "stream"], paint: { "line-color": e.water, "line-width": 0.5 } }, { id: "water_river", type: "line", source: a, "source-layer": "water", minzoom: 9, filter: ["in", "kind", "river"], paint: { "line-color": e.water, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 9, 0, 9.5, 1, 18, 12] } }, { id: "landuse_pedestrian", type: "fill", source: a, "source-layer": "landuse", filter: ["in", "kind", "pedestrian", "dam"], paint: { "fill-color": e.pedestrian } }, { id: "landuse_pier", type: "fill", source: a, "source-layer": "landuse", filter: ["==", "kind", "pier"], paint: { "fill-color": e.pier } }, { id: "roads_tunnels_other_casing", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["in", "kind", "other", "path"]], paint: { "line-color": e.tunnel_other_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 14, 0, 20, 7] } }, { id: "roads_tunnels_minor_casing", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["==", "kind", "minor_road"]], paint: { "line-color": e.tunnel_minor_casing, "line-dasharray": [3, 2], "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0, 12.5, 0.5, 15, 2, 18, 11], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 12, 0, 12.5, 1] } }, { id: "roads_tunnels_link_casing", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["has", "is_link"]], paint: { "line-color": e.tunnel_link_casing, "line-dasharray": [3, 2], "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1, 18, 11], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 12, 0, 12.5, 1] } }, { id: "roads_tunnels_major_casing", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "major_road"]], paint: { "line-color": e.tunnel_major_casing, "line-dasharray": [3, 2], "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0, 7.5, 0.5, 18, 13], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 9, 0, 9.5, 1] } }, { id: "roads_tunnels_highway_casing", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "highway"], ["!has", "is_link"]], paint: { "line-color": e.tunnel_highway_casing, "line-dasharray": [6, 0.5], "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 3.5, 0.5, 18, 15], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0, 7.5, 1, 20, 15] } }, { id: "roads_tunnels_other", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["in", "kind", "other", "path"]], paint: { "line-color": e.tunnel_other, "line-dasharray": [4.5, 0.5], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 14, 0, 20, 7] } }, { id: "roads_tunnels_minor", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["==", "kind", "minor_road"]], paint: { "line-color": e.tunnel_minor, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0, 12.5, 0.5, 15, 2, 18, 11] } }, { id: "roads_tunnels_link", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["has", "is_link"]], paint: { "line-color": e.tunnel_minor, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1, 18, 11] } }, { id: "roads_tunnels_major", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["==", "kind", "major_road"]], paint: { "line-color": e.tunnel_major, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 6, 0, 12, 1.6, 15, 3, 18, 13] } }, { id: "roads_tunnels_highway", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_tunnel"], ["==", ["get", "kind"], "highway"], ["!", ["has", "is_link"]]], paint: { "line-color": e.tunnel_highway, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 6, 1.1, 12, 1.6, 15, 5, 18, 15] } }, { id: "buildings", type: "fill", source: a, "source-layer": "buildings", filter: ["in", "kind", "building", "building_part"], paint: { "fill-color": e.buildings, "fill-opacity": 0.5 } }, { id: "roads_pier", type: "line", source: a, "source-layer": "roads", filter: ["==", "kind_detail", "pier"], paint: { "line-color": e.pier, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 12, 0, 12.5, 0.5, 20, 16] } }, { id: "roads_minor_service_casing", type: "line", source: a, "source-layer": "roads", minzoom: 13, filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "minor_road"], ["==", "kind_detail", "service"]], paint: { "line-color": e.minor_service_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 18, 8], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 0.8] } }, { id: "roads_minor_casing", type: "line", source: a, "source-layer": "roads", filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "minor_road"], ["!=", "kind_detail", "service"]], paint: { "line-color": e.minor_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0, 12.5, 0.5, 15, 2, 18, 11], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 12, 0, 12.5, 1] } }, { id: "roads_link_casing", type: "line", source: a, "source-layer": "roads", minzoom: 13, filter: ["has", "is_link"], paint: { "line-color": e.minor_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1, 18, 11], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1.5] } }, { id: "roads_major_casing_late", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "major_road"]], paint: { "line-color": e.major_casing_late, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 6, 0, 12, 1.6, 15, 3, 18, 13], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 9, 0, 9.5, 1] } }, { id: "roads_highway_casing_late", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "highway"], ["!has", "is_link"]], paint: { "line-color": e.highway_casing_late, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 3.5, 0.5, 18, 15], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0, 7.5, 1, 20, 15] } }, { id: "roads_other", type: "line", source: a, "source-layer": "roads", filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["in", "kind", "other", "path"], ["!=", "kind_detail", "pier"]], paint: { "line-color": e.other, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 14, 0.5, 20, 12] } }, { id: "roads_link", type: "line", source: a, "source-layer": "roads", filter: ["has", "is_link"], paint: { "line-color": e.link, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1, 18, 11] } }, { id: "roads_minor_service", type: "line", source: a, "source-layer": "roads", filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "minor_road"], ["==", "kind_detail", "service"]], paint: { "line-color": e.minor_service, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 18, 8] } }, { id: "roads_minor", type: "line", source: a, "source-layer": "roads", filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "minor_road"], ["!=", "kind_detail", "service"]], paint: { "line-color": ["interpolate", ["exponential", 1.6], ["zoom"], 11, e.minor_a, 16, e.minor_b], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0, 12.5, 0.5, 15, 2, 18, 11] } }, { id: "roads_major_casing_early", type: "line", source: a, "source-layer": "roads", maxzoom: 12, filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "major_road"]], paint: { "line-color": e.major_casing_early, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0, 7.5, 0.5, 18, 13], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 9, 0, 9.5, 1] } }, { id: "roads_major", type: "line", source: a, "source-layer": "roads", filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "major_road"]], paint: { "line-color": e.major, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 6, 0, 12, 1.6, 15, 3, 18, 13] } }, { id: "roads_highway_casing_early", type: "line", source: a, "source-layer": "roads", maxzoom: 12, filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "highway"], ["!has", "is_link"]], paint: { "line-color": e.highway_casing_early, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 3.5, 0.5, 18, 15], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0, 7.5, 1] } }, { id: "roads_highway", type: "line", source: a, "source-layer": "roads", filter: ["all", ["!has", "is_tunnel"], ["!has", "is_bridge"], ["==", "kind", "highway"], ["!has", "is_link"]], paint: { "line-color": e.highway, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 6, 1.1, 12, 1.6, 15, 5, 18, 15] } }, { id: "roads_rail", type: "line", source: a, "source-layer": "roads", filter: ["==", "kind", "rail"], paint: { "line-dasharray": [0.3, 0.75], "line-opacity": 0.5, "line-color": e.railway, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 6, 0.15, 18, 9] } }, { id: "boundaries_country", type: "line", source: a, "source-layer": "boundaries", filter: ["<=", "kind_detail", 2], paint: { "line-color": e.boundaries, "line-width": 0.7, "line-dasharray": ["step", ["zoom"], ["literal", [2, 0]], 4, ["literal", [2, 1]]] } }, { id: "boundaries", type: "line", source: a, "source-layer": "boundaries", filter: [">", "kind_detail", 2], paint: { "line-color": e.boundaries, "line-width": 0.4, "line-dasharray": ["step", ["zoom"], ["literal", [2, 0]], 4, ["literal", [2, 1]]] } }, { id: "roads_bridges_other_casing", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["in", "kind", "other", "path"]], paint: { "line-color": e.bridges_other_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 14, 0, 20, 7] } }, { id: "roads_bridges_link_casing", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["has", "is_link"]], paint: { "line-color": e.bridges_minor_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1, 18, 11], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 12, 0, 12.5, 1.5] } }, { id: "roads_bridges_minor_casing", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["==", "kind", "minor_road"]], paint: { "line-color": e.bridges_minor_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0, 12.5, 0.5, 15, 2, 18, 11], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 0.8] } }, { id: "roads_bridges_major_casing", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["==", "kind", "major_road"]], paint: { "line-color": e.bridges_major_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0, 7.5, 0.5, 18, 10], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 9, 0, 9.5, 1.5] } }, { id: "roads_bridges_other", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["in", "kind", "other", "path"]], paint: { "line-color": e.bridges_other, "line-dasharray": [2, 1], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 14, 0, 20, 7] } }, { id: "roads_bridges_minor", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["==", "kind", "minor_road"]], paint: { "line-color": e.bridges_minor, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0, 12.5, 0.5, 15, 2, 18, 11] } }, { id: "roads_bridges_link", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["has", "is_link"]], paint: { "line-color": e.bridges_minor, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 13, 0, 13.5, 1, 18, 11] } }, { id: "roads_bridges_major", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["==", "kind", "major_road"]], paint: { "line-color": e.bridges_major, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 6, 0, 12, 1.6, 15, 3, 18, 13] } }, { id: "roads_bridges_highway_casing", type: "line", source: a, "source-layer": "roads", minzoom: 12, filter: ["all", ["has", "is_bridge"], ["==", "kind", "highway"], ["!has", "is_link"]], paint: { "line-color": e.bridges_highway_casing, "line-gap-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 3.5, 0.5, 18, 15], "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0, 7.5, 1, 20, 15] } }, { id: "roads_bridges_highway", type: "line", source: a, "source-layer": "roads", filter: ["all", ["has", "is_bridge"], ["==", "kind", "highway"], ["!has", "is_link"]], paint: { "line-color": e.bridges_highway, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 3, 0, 6, 1.1, 12, 1.6, 15, 5, 18, 15] } }];
  }
  r(f, "nolabels_layers");
  function p(a, e, n, i2) {
    return [{ id: "address_label", type: "symbol", source: a, "source-layer": "buildings", minzoom: 18, filter: ["==", "kind", "address"], layout: { "symbol-placement": "point", "text-font": [e.italic || "Noto Sans Italic"], "text-field": ["get", "addr_housenumber"], "text-size": 12 }, paint: { "text-color": e.address_label, "text-halo-color": e.address_label_halo, "text-halo-width": 1 } }, { id: "water_waterway_label", type: "symbol", source: a, "source-layer": "water", minzoom: 13, filter: ["in", "kind", "river", "stream"], layout: { "symbol-placement": "line", "text-font": [e.italic || "Noto Sans Italic"], "text-field": o(n, i2, e.regular), "text-size": 12, "text-letter-spacing": 0.2 }, paint: { "text-color": e.ocean_label, "text-halo-color": e.water, "text-halo-width": 1 } }, { id: "roads_oneway", type: "symbol", source: a, "source-layer": "roads", minzoom: 16, filter: ["==", ["get", "oneway"], "yes"], layout: { "symbol-placement": "line", "icon-image": "arrow", "icon-rotate": 90, "symbol-spacing": 100 } }, { id: "roads_labels_minor", type: "symbol", source: a, "source-layer": "roads", minzoom: 15, filter: ["in", "kind", "minor_road", "other", "path"], layout: { "symbol-sort-key": ["get", "min_zoom"], "symbol-placement": "line", "text-font": [e.regular || "Noto Sans Regular"], "text-field": o(n, i2, e.regular), "text-size": 12 }, paint: { "text-color": e.roads_label_minor, "text-halo-color": e.roads_label_minor_halo, "text-halo-width": 1 } }, { id: "water_label_ocean", type: "symbol", source: a, "source-layer": "water", filter: ["in", "kind", "sea", "ocean", "bay", "strait", "fjord"], layout: { "text-font": [e.italic || "Noto Sans Italic"], "text-field": o(n, i2, e.regular), "text-size": ["interpolate", ["linear"], ["zoom"], 3, 10, 10, 12], "text-letter-spacing": 0.1, "text-max-width": 9, "text-transform": "uppercase" }, paint: { "text-color": e.ocean_label, "text-halo-width": 1, "text-halo-color": e.water } }, { id: "earth_label_islands", type: "symbol", source: a, "source-layer": "earth", filter: ["in", "kind", "island"], layout: { "text-font": [e.italic || "Noto Sans Italic"], "text-field": o(n, i2, e.regular), "text-size": 10, "text-letter-spacing": 0.1, "text-max-width": 8 }, paint: { "text-color": e.subplace_label, "text-halo-color": e.subplace_label_halo, "text-halo-width": 1 } }, { id: "water_label_lakes", type: "symbol", source: a, "source-layer": "water", filter: ["in", "kind", "lake", "water"], layout: { "text-font": [e.italic || "Noto Sans Italic"], "text-field": o(n, i2, e.regular), "text-size": ["interpolate", ["linear"], ["zoom"], 3, 10, 6, 12, 10, 12], "text-letter-spacing": 0.1, "text-max-width": 9 }, paint: { "text-color": e.ocean_label, "text-halo-color": e.water, "text-halo-width": 1 } }, { id: "roads_shields", type: "symbol", source: a, "source-layer": "roads", filter: ["all", ["in", ["get", "kind"], ["literal", ["highway", "major_road"]]], ["has", "shield_text"], ["<=", ["length", ["get", "shield_text"]], 5]], layout: { "icon-image": ["match", ["get", "network"], "US:I", ["concat", "US:I-", ["length", ["get", "shield_text"]], "char"], "NL:S-road", ["concat", "NL:S-road-", ["length", ["get", "shield_text"]], "char"], ["concat", "generic_shield-", ["length", ["get", "shield_text"]], "char"]], "text-field": ["get", "shield_text"], "text-font": [e.bold || "Noto Sans Medium"], "text-size": 8, "icon-size": 0.8, "symbol-placement": "line", "icon-rotation-alignment": "viewport", "text-rotation-alignment": "viewport" }, paint: { "text-color": e.roads_label_major } }, { id: "roads_labels_major", type: "symbol", source: a, "source-layer": "roads", minzoom: 11, filter: ["in", "kind", "highway", "major_road"], layout: { "symbol-sort-key": ["get", "min_zoom"], "symbol-placement": "line", "text-font": [e.regular || "Noto Sans Regular"], "text-field": o(n, i2, e.regular), "text-size": 12 }, paint: { "text-color": e.roads_label_major, "text-halo-color": e.roads_label_major_halo, "text-halo-width": 1 } }, ...e.pois ? [{ id: "pois", type: "symbol", source: a, "source-layer": "pois", filter: ["all", ["in", ["get", "kind"], ["literal", ["beach", "forest", "marina", "park", "peak", "zoo", "garden", "bench", "aerodrome", "station", "bus_stop", "ferry_terminal", "stadium", "university", "library", "school", "animal", "toilets", "drinking_water", "post_office", "building", "townhall", "restaurant", "fast_food", "cafe", "bar", "supermarket", "convenience", "books", "beauty", "electronics", "clothes", "attraction", "museum", "theatre", "artwork"]]], [">=", ["zoom"], ["+", ["get", "min_zoom"], 0]]], layout: { "icon-image": ["match", ["get", "kind"], "station", "train_station", ["get", "kind"]], "text-font": [e.regular || "Noto Sans Regular"], "text-justify": "auto", "text-field": o(n, i2, e.regular), "text-size": ["interpolate", ["linear"], ["zoom"], 17, 10, 19, 16], "text-max-width": 8, "text-offset": [1.1, 0], "text-variable-anchor": ["left", "right"] }, paint: { "text-color": ["case", ["in", ["get", "kind"], ["literal", ["beach", "forest", "marina", "park", "peak", "zoo", "garden", "bench"]]], e.pois.green, ["in", ["get", "kind"], ["literal", ["aerodrome", "station", "bus_stop", "ferry_terminal"]]], e.pois.lapis, ["in", ["get", "kind"], ["literal", ["stadium", "university", "library", "school", "animal", "toilets", "drinking_water", "post_office", "building", "townhall"]]], e.pois.slategray, ["in", ["get", "kind"], ["literal", ["supermarket", "convenience", "books", "beauty", "electronics", "clothes"]]], e.pois.blue, ["in", ["get", "kind"], ["literal", ["restaurant", "fast_food", "cafe", "bar"]]], e.pois.tangerine, ["in", ["get", "kind"], ["literal", ["attraction", "museum", "theatre", "artwork"]]], e.pois.pink, e.earth], "text-halo-color": e.earth, "text-halo-width": 1 } }] : [], { id: "places_subplace", type: "symbol", source: a, "source-layer": "places", filter: ["in", "kind", "neighbourhood", "macrohood"], layout: { "symbol-sort-key": ["case", ["has", "sort_key"], ["get", "sort_key"], ["get", "min_zoom"]], "text-field": o(n, i2, e.regular), "text-font": [e.regular || "Noto Sans Regular"], "text-max-width": 7, "text-letter-spacing": 0.1, "text-padding": ["interpolate", ["linear"], ["zoom"], 5, 2, 8, 4, 12, 18, 15, 20], "text-size": ["interpolate", ["exponential", 1.2], ["zoom"], 11, 8, 14, 14, 18, 24], "text-transform": "uppercase" }, paint: { "text-color": e.subplace_label, "text-halo-color": e.subplace_label_halo, "text-halo-width": 1 } }, { id: "places_region", type: "symbol", source: a, "source-layer": "places", filter: ["==", "kind", "region"], layout: { "symbol-sort-key": ["get", "sort_key"], "text-field": ["step", ["zoom"], ["coalesce", ["get", "ref:en"], ["get", "ref"]], 6, o(n, i2, e.regular)], "text-font": [e.regular || "Noto Sans Regular"], "text-size": ["interpolate", ["linear"], ["zoom"], 3, 11, 7, 16], "text-radial-offset": 0.2, "text-anchor": "center", "text-transform": "uppercase" }, paint: { "text-color": e.state_label, "text-halo-color": e.state_label_halo, "text-halo-width": 1 } }, { id: "places_locality", type: "symbol", source: a, "source-layer": "places", filter: ["==", "kind", "locality"], layout: { "icon-image": ["step", ["zoom"], ["case", ["==", ["get", "capital"], "yes"], "capital", "townspot"], 8, ""], "icon-size": 0.7, "text-field": o(n, i2, e.regular), "text-font": ["case", ["<=", ["get", "min_zoom"], 5], ["literal", [e.bold || "Noto Sans Medium"]], ["literal", [e.regular || "Noto Sans Regular"]]], "symbol-sort-key": ["case", ["has", "sort_key"], ["get", "sort_key"], ["get", "min_zoom"]], "text-padding": ["interpolate", ["linear"], ["zoom"], 5, 3, 8, 7, 12, 11], "text-size": ["interpolate", ["linear"], ["zoom"], 2, ["case", ["<", ["get", "population_rank"], 13], 8, [">=", ["get", "population_rank"], 13], 13, 0], 4, ["case", ["<", ["get", "population_rank"], 13], 10, [">=", ["get", "population_rank"], 13], 15, 0], 6, ["case", ["<", ["get", "population_rank"], 12], 11, [">=", ["get", "population_rank"], 12], 17, 0], 8, ["case", ["<", ["get", "population_rank"], 11], 11, [">=", ["get", "population_rank"], 11], 18, 0], 10, ["case", ["<", ["get", "population_rank"], 9], 12, [">=", ["get", "population_rank"], 9], 20, 0], 15, ["case", ["<", ["get", "population_rank"], 8], 12, [">=", ["get", "population_rank"], 8], 22, 0]], "icon-padding": ["interpolate", ["linear"], ["zoom"], 0, 0, 8, 4, 10, 8, 12, 6, 22, 2], "text-justify": "auto", "text-variable-anchor": ["step", ["zoom"], ["literal", ["bottom", "left", "right", "top"]], 8, ["literal", ["center"]]], "text-radial-offset": 0.3 }, paint: { "text-color": e.city_label, "text-halo-color": e.city_label_halo, "text-halo-width": 1 } }, { id: "places_country", type: "symbol", source: a, "source-layer": "places", filter: ["==", "kind", "country"], layout: { "symbol-sort-key": ["case", ["has", "sort_key"], ["get", "sort_key"], ["get", "min_zoom"]], "text-field": d2(n, i2), "text-font": [e.bold || "Noto Sans Medium"], "text-size": ["interpolate", ["linear"], ["zoom"], 2, ["case", ["<", ["get", "population_rank"], 10], 8, [">=", ["get", "population_rank"], 10], 12, 0], 6, ["case", ["<", ["get", "population_rank"], 8], 10, [">=", ["get", "population_rank"], 8], 18, 0], 8, ["case", ["<", ["get", "population_rank"], 7], 11, [">=", ["get", "population_rank"], 7], 20, 0]], "icon-padding": ["interpolate", ["linear"], ["zoom"], 0, 2, 14, 2, 16, 20, 17, 2, 22, 2], "text-transform": "uppercase" }, paint: { "text-color": e.country_label, "text-halo-color": e.earth, "text-halo-width": 1 } }];
  }
  r(p, "labels_layers");
  var m = { background: "#cccccc", earth: "#e2dfda", park_a: "#cfddd5", park_b: "#9cd3b4", hospital: "#e4dad9", industrial: "#d1dde1", school: "#e4ded7", wood_a: "#d0ded0", wood_b: "#a0d9a0", pedestrian: "#e3e0d4", scrub_a: "#cedcd7", scrub_b: "#99d2bb", glacier: "#e7e7e7", sand: "#e2e0d7", beach: "#e8e4d0", aerodrome: "#dadbdf", runway: "#e9e9ed", water: "#80deea", zoo: "#c6dcdc", military: "#dcdcdc", tunnel_other_casing: "#e0e0e0", tunnel_minor_casing: "#e0e0e0", tunnel_link_casing: "#e0e0e0", tunnel_major_casing: "#e0e0e0", tunnel_highway_casing: "#e0e0e0", tunnel_other: "#d5d5d5", tunnel_minor: "#d5d5d5", tunnel_link: "#d5d5d5", tunnel_major: "#d5d5d5", tunnel_highway: "#d5d5d5", pier: "#e0e0e0", buildings: "#cccccc", minor_service_casing: "#e0e0e0", minor_casing: "#e0e0e0", link_casing: "#e0e0e0", major_casing_late: "#e0e0e0", highway_casing_late: "#e0e0e0", other: "#ebebeb", minor_service: "#ebebeb", minor_a: "#ebebeb", minor_b: "#ffffff", link: "#ffffff", major_casing_early: "#e0e0e0", major: "#ffffff", highway_casing_early: "#e0e0e0", highway: "#ffffff", railway: "#a7b1b3", boundaries: "#adadad", bridges_other_casing: "#e0e0e0", bridges_minor_casing: "#e0e0e0", bridges_link_casing: "#e0e0e0", bridges_major_casing: "#e0e0e0", bridges_highway_casing: "#e0e0e0", bridges_other: "#ebebeb", bridges_minor: "#ffffff", bridges_link: "#ffffff", bridges_major: "#f5f5f5", bridges_highway: "#ffffff", roads_label_minor: "#91888b", roads_label_minor_halo: "#ffffff", roads_label_major: "#938a8d", roads_label_major_halo: "#ffffff", ocean_label: "#728dd4", subplace_label: "#8f8f8f", subplace_label_halo: "#e0e0e0", city_label: "#5c5c5c", city_label_halo: "#e0e0e0", state_label: "#b3b3b3", state_label_halo: "#e0e0e0", country_label: "#a3a3a3", address_label: "#91888b", address_label_halo: "#ffffff", pois: { blue: "#1A8CBD", green: "#20834D", lapis: "#315BCF", pink: "#EF56BA", red: "#F2567A", slategray: "#6A5B8F", tangerine: "#CB6704", turquoise: "#00C3D4" }, landcover: { grassland: "rgba(210, 239, 207, 1)", barren: "rgba(255, 243, 215, 1)", urban_area: "rgba(230, 230, 230, 1)", farmland: "rgba(216, 239, 210, 1)", glacier: "rgba(255, 255, 255, 1)", scrub: "rgba(234, 239, 210, 1)", forest: "rgba(196, 231, 210, 1)" } };
  var b2 = { background: "#34373d", earth: "#1f1f1f", park_a: "#1c2421", park_b: "#192a24", hospital: "#252424", industrial: "#222222", school: "#262323", wood_a: "#202121", wood_b: "#202121", pedestrian: "#1e1e1e", scrub_a: "#222323", scrub_b: "#222323", glacier: "#1c1c1c", sand: "#212123", beach: "#28282a", aerodrome: "#1e1e1e", runway: "#333333", water: "#31353f", zoo: "#222323", military: "#242323", tunnel_other_casing: "#141414", tunnel_minor_casing: "#141414", tunnel_link_casing: "#141414", tunnel_major_casing: "#141414", tunnel_highway_casing: "#141414", tunnel_other: "#292929", tunnel_minor: "#292929", tunnel_link: "#292929", tunnel_major: "#292929", tunnel_highway: "#292929", pier: "#333333", buildings: "#111111", minor_service_casing: "#1f1f1f", minor_casing: "#1f1f1f", link_casing: "#1f1f1f", major_casing_late: "#1f1f1f", highway_casing_late: "#1f1f1f", other: "#333333", minor_service: "#333333", minor_a: "#3d3d3d", minor_b: "#333333", link: "#3d3d3d", major_casing_early: "#1f1f1f", major: "#3d3d3d", highway_casing_early: "#1f1f1f", highway: "#474747", railway: "#000000", boundaries: "#5b6374", bridges_other_casing: "#2b2b2b", bridges_minor_casing: "#1f1f1f", bridges_link_casing: "#1f1f1f", bridges_major_casing: "#1f1f1f", bridges_highway_casing: "#1f1f1f", bridges_other: "#333333", bridges_minor: "#333333", bridges_link: "#3d3d3d", bridges_major: "#3d3d3d", bridges_highway: "#474747", roads_label_minor: "#525252", roads_label_minor_halo: "#1f1f1f", roads_label_major: "#666666", roads_label_major_halo: "#1f1f1f", ocean_label: "#717784", subplace_label: "#525252", subplace_label_halo: "#1f1f1f", city_label: "#7a7a7a", city_label_halo: "#212121", state_label: "#3d3d3d", state_label_halo: "#1f1f1f", country_label: "#5c5c5c", address_label: "#525252", address_label_halo: "#1f1f1f", pois: { blue: "#4299BB", green: "#30C573", lapis: "#2B5CEA", pink: "#EF56BA", red: "#F2567A", slategray: "#93939F", tangerine: "#F19B6E", turquoise: "#00C3D4" }, landcover: { grassland: "rgba(30, 41, 31, 1)", barren: "rgba(38, 38, 36, 1)", urban_area: "rgba(28, 28, 28, 1)", farmland: "rgba(31, 36, 32, 1)", glacier: "rgba(43, 43, 43, 1)", scrub: "rgba(34, 36, 30, 1)", forest: "rgba(28, 41, 37, 1)" } };
  var h2 = { background: "#ffffff", earth: "#ffffff", park_a: "#fcfcfc", park_b: "#fcfcfc", hospital: "#f8f8f8", industrial: "#fcfcfc", school: "#f8f8f8", wood_a: "#fafafa", wood_b: "#fafafa", pedestrian: "#fdfdfd", scrub_a: "#fafafa", scrub_b: "#fafafa", glacier: "#fcfcfc", sand: "#fafafa", beach: "#f6f6f6", aerodrome: "#fdfdfd", runway: "#efefef", water: "#dcdcdc", zoo: "#f7f7f7", military: "#fcfcfc", tunnel_other_casing: "#d6d6d6", tunnel_minor_casing: "#fcfcfc", tunnel_link_casing: "#fcfcfc", tunnel_major_casing: "#fcfcfc", tunnel_highway_casing: "#fcfcfc", tunnel_other: "#d6d6d6", tunnel_minor: "#d6d6d6", tunnel_link: "#d6d6d6", tunnel_major: "#d6d6d6", tunnel_highway: "#d6d6d6", pier: "#efefef", buildings: "#efefef", minor_service_casing: "#ffffff", minor_casing: "#ffffff", link_casing: "#ffffff", major_casing_late: "#ffffff", highway_casing_late: "#ffffff", other: "#f5f5f5", minor_service: "#f5f5f5", minor_a: "#ebebeb", minor_b: "#f5f5f5", link: "#ebebeb", major_casing_early: "#ffffff", major: "#ebebeb", highway_casing_early: "#ffffff", highway: "#ebebeb", railway: "#d6d6d6", boundaries: "#adadad", bridges_other_casing: "#ffffff", bridges_minor_casing: "#ffffff", bridges_link_casing: "#ffffff", bridges_major_casing: "#ffffff", bridges_highway_casing: "#ffffff", bridges_other: "#f5f5f5", bridges_minor: "#f5f5f5", bridges_link: "#ebebeb", bridges_major: "#ebebeb", bridges_highway: "#ebebeb", roads_label_minor: "#adadad", roads_label_minor_halo: "#ffffff", roads_label_major: "#999999", roads_label_major_halo: "#ffffff", ocean_label: "#adadad", subplace_label: "#8f8f8f", subplace_label_halo: "#ffffff", city_label: "#5c5c5c", city_label_halo: "#ffffff", state_label: "#b3b3b3", state_label_halo: "#ffffff", country_label: "#b8b8b8", address_label: "#adadad", address_label_halo: "#ffffff" };
  var u = { background: "#a3a3a3", earth: "#cccccc", park_a: "#c2c2c2", park_b: "#c2c2c2", hospital: "#d0d0d0", industrial: "#c6c6c6", school: "#d0d0d0", wood_a: "#c2c2c2", wood_b: "#c2c2c2", pedestrian: "#c4c4c4", scrub_a: "#c2c2c2", scrub_b: "#c2c2c2", glacier: "#d2d2d2", sand: "#d2d2d2", beach: "#d2d2d2", aerodrome: "#c9c9c9", runway: "#f5f5f5", water: "#a3a3a3", zoo: "#c7c7c7", military: "#bfbfbf", tunnel_other_casing: "#b8b8b8", tunnel_minor_casing: "#b8b8b8", tunnel_link_casing: "#b8b8b8", tunnel_major_casing: "#b8b8b8", tunnel_highway_casing: "#b8b8b8", tunnel_other: "#d6d6d6", tunnel_minor: "#d6d6d6", tunnel_link: "#d6d6d6", tunnel_major: "#d6d6d6", tunnel_highway: "#d6d6d6", pier: "#b8b8b8", buildings: "#e0e0e0", minor_service_casing: "#cccccc", minor_casing: "#cccccc", link_casing: "#cccccc", major_casing_late: "#cccccc", highway_casing_late: "#cccccc", other: "#e0e0e0", minor_service: "#e0e0e0", minor_a: "#ebebeb", minor_b: "#e0e0e0", link: "#ebebeb", major_casing_early: "#cccccc", major: "#ebebeb", highway_casing_early: "#cccccc", highway: "#ebebeb", railway: "#f5f5f5", boundaries: "#5c5c5c", bridges_other_casing: "#cccccc", bridges_minor_casing: "#cccccc", bridges_link_casing: "#cccccc", bridges_major_casing: "#cccccc", bridges_highway_casing: "#cccccc", bridges_other: "#e0e0e0", bridges_minor: "#e0e0e0", bridges_link: "#ebebeb", bridges_major: "#ebebeb", bridges_highway: "#ebebeb", roads_label_minor: "#999999", roads_label_minor_halo: "#e0e0e0", roads_label_major: "#8f8f8f", roads_label_major_halo: "#ebebeb", ocean_label: "#7a7a7a", subplace_label: "#7a7a7a", subplace_label_halo: "#cccccc", city_label: "#474747", city_label_halo: "#cccccc", state_label: "#999999", state_label_halo: "#cccccc", country_label: "#858585", address_label: "#999999", address_label_halo: "#e0e0e0" };
  var y2 = { background: "#2b2b2b", earth: "#141414", park_a: "#181818", park_b: "#181818", hospital: "#1d1d1d", industrial: "#101010", school: "#111111", wood_a: "#1a1a1a", wood_b: "#1a1a1a", pedestrian: "#191919", scrub_a: "#1c1c1c", scrub_b: "#1c1c1c", glacier: "#191919", sand: "#161616", beach: "#1f1f1f", aerodrome: "#191919", runway: "#323232", water: "#333333", zoo: "#191919", military: "#121212", tunnel_other_casing: "#101010", tunnel_minor_casing: "#101010", tunnel_link_casing: "#101010", tunnel_major_casing: "#101010", tunnel_highway_casing: "#101010", tunnel_other: "#292929", tunnel_minor: "#292929", tunnel_link: "#292929", tunnel_major: "#292929", tunnel_highway: "#292929", pier: "#0a0a0a", buildings: "#0a0a0a", minor_service_casing: "#141414", minor_casing: "#141414", link_casing: "#141414", major_casing_late: "#141414", highway_casing_late: "#141414", other: "#1f1f1f", minor_service: "#1f1f1f", minor_a: "#292929", minor_b: "#1f1f1f", link: "#1f1f1f", major_casing_early: "#141414", major: "#292929", highway_casing_early: "#141414", highway: "#292929", railway: "#292929", boundaries: "#707070", bridges_other_casing: "#141414", bridges_minor_casing: "#141414", bridges_link_casing: "#141414", bridges_major_casing: "#141414", bridges_highway_casing: "#141414", bridges_other: "#1f1f1f", bridges_minor: "#1f1f1f", bridges_link: "#292929", bridges_major: "#292929", bridges_highway: "#292929", roads_label_minor: "#525252", roads_label_minor_halo: "#141414", roads_label_major: "#5c5c5c", roads_label_major_halo: "#141414", ocean_label: "#707070", subplace_label: "#5c5c5c", subplace_label_halo: "#141414", city_label: "#999999", city_label_halo: "#141414", state_label: "#3d3d3d", state_label_halo: "#141414", country_label: "#707070", address_label: "#525252", address_label_halo: "#141414" };
  function C2(a) {
    switch (a) {
      case "light":
        return m;
      case "dark":
        return b2;
      case "white":
        return h2;
      case "grayscale":
        return u;
      case "black":
        return y2;
    }
    throw new Error("Flavor not found");
  }
  r(C2, "namedFlavor");
  function R3(a, e, n) {
    let i2 = [];
    return n != null && n.labelsOnly || (i2 = f(a, e)), n != null && n.lang && (i2 = i2.concat(p(a, e, n.lang))), i2;
  }
  r(R3, "layers");

  // src/vector_entry.js
  window.TRIP_VECTOR = { Protocol: B, PMTiles: w, FileSource: k, layers: R3, namedFlavor: C2 };
})();
