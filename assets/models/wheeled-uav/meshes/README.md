# 車輪付きドローンの表示用メッシュ / Display meshes for the wheeled drone

シミュレータのデモ（`/simulator/`）で，現在の箱・円柱の代わりに機体の形状を描くための STL の置き場所です。
このフォルダに STL を置いてください。階層（サブフォルダ）はそのままで構いません。

## 置き方

- **独立して動く部品ごとに 1 ファイル**にしてください。最低限，次の 3 つが分かれていれば描画できます。
  - 機体本体（フレーム・アーム・モータ・電装をまとめたもの）
  - 左車輪
  - 右車輪
  - プロペラ 4 枚（任意。分かれていれば回転させて描けます）
- 形式は **バイナリ STL** が望ましいですが，ASCII STL でも読めます。
- **座標系と原点**：機体本体は，重心（MuJoCo モデルの body 原点）を原点に，x 前方・y 左・z 上が理想です。
  そうなっていなくても，CAD の原点と軸の向き（例：「原点は底面中心，z 上，x 前」）と**単位（mm か m か）**を
  教えていただければ，読み込み側で合わせます。
- 車輪は車軸を y 軸に取り，車輪中心を原点にしてください（こちらも，違っていれば申し送りで対応します）。
- **サイズ**：表示専用なので，細かいネジやフィレットは不要です。合計 1〜2 MB 以下が目安です。
  重い場合はこちらで面数を減らします（元の STL はそのまま置いてください）。

## Placement

Put the STL files here, keeping whatever folder hierarchy they already have.
One file per independently moving part: the airframe (frame, arms, motors, electronics as one piece),
the left wheel, the right wheel, and optionally the four propellers. Binary STL is preferred.
Ideal frames: airframe origin at the center of mass with x forward, y left, z up; each wheel with its
axle along y and its origin at the wheel center. If the CAD frames differ, note the origin, axes and
units (mm or m) and the loader will compensate. Display only, so coarse geometry is fine; aim for
1–2 MB in total.

## メモ

このフォルダの中身はサイトにそのまま配信されます（`assets/` 以下は公開対象です）。
