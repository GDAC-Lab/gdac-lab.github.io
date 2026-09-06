# 車輪付きドローンの表示用メッシュ / Display meshes for the wheeled drone

シミュレータのデモ（`/simulator/`）で機体を描くための CAD です。研究室で実機を採寸して
起こしたもので，`CAD-README.md` に元の配布時の説明が入っています。

このフォルダは **サイトには配信されません**（`_config.yml` の `exclude:` に入れてあります）。
公開されるのは，この CAD から生成した一つのファイル `../drone-mesh.bin`（約 250 KB）だけです。
8 MB の STL を訪問者に転送する理由はないためです。

## ファイル

| ファイル | 内容 |
|---|---|
| `frame.stl` | 機体本体。車輪の軸受けまで含みます |
| `wheel_l.stl` / `wheel_r.stl` | 左右の車輪（CAD 半径 0.142 m） |
| `propeller_cw.stl` / `propeller_ccw.stl` | 3 枚羽根のプロペラ。ハブがメッシュ原点 |
| `QAV250.stl` | 組み立て済みの一体メッシュ。描画には使っていません（参考用） |

座標系は機体座標系（**x 前方，y 左，z 上**），単位は **mm**。バイナリ STL です。

## 作り直し方

CAD を差し替えたら，次を実行して `../drone-mesh.bin` を作り直し，両方をコミットしてください。

```
python3 -m pip install numpy fast-simplification
python3 scripts/build_drone_mesh.py            # --check を付けると書き込まずに数値だけ出ます
```

スクリプトは，頂点を溶接して三角形を削り（本体 36,000 → 6,000 など），浅い稜線だけを
滑らかにした法線を付けて，位置・法線・インデックスを一つのバイナリにまとめます。
形状の誤差は本体で 2 mm 以下です。デモ中の機体は画面上で数百ピクセルなので，
これ以上の細かさは 1 ピクセルより小さくなります。

部品の置き方（どの当たり判定の代わりに描くか，ロータの位置，車輪の拡大率）は
すべてこのスクリプトが `drone-mesh.bin` のヘッダに書き込み，描画側
（`assets/js/simulator/drone-mesh.js`）はそれを読むだけです。JavaScript 側に機体の
寸法は書かれていません。

## 車輪の半径について

MuJoCo モデルの当たり判定の車輪は半径 0.15 m ですが，CAD の車輪は 0.142 m です。
デモの要点は「車輪が壁に触れること」なので，描画では車輪を 0.15 m に合わせて
6% 拡大しています（`WHEEL_RADIUS_SIM` / `WHEEL_RADIUS_CAD`）。そうしないと，
壁に押し付けているのに車輪が 8 mm 浮いて見えます。

---

## English

The CAD the demo's vehicle is drawn from, measured from the lab's own airframe;
`CAD-README.md` is the note that came with it.

This folder is **not published** (see `exclude:` in `_config.yml`). Only the single
file built from it, `../drone-mesh.bin` (about 250 KB), is served: there is no reason
to send visitors 8 MB of STL.

Parts are in the vehicle body frame (**x forward, y left, z up**) in **millimetres**,
as binary STL. `QAV250.stl` is the assembled body, kept for reference but not used.

To rebuild after changing the CAD, run `python3 scripts/build_drone_mesh.py` (it needs
`numpy` and `fast-simplification`) and commit both the STL and the regenerated bundle.
The script welds, decimates, computes angle-limited normals and packs the result; the
frame stays within 2 mm of the original, well under a pixel at the size the demo draws.
Everything the renderer needs in order to place a part is written into the bundle
header, so no vehicle dimension is hard-coded in the JavaScript.

The collision wheel in the MuJoCo model is 0.15 m and the CAD wheel is 0.142 m, so the
drawn wheel is scaled up by 6% to meet the wall where the physics says it does.
