// Labels and hover help share the same keys in both locales.
const row=(en,ja,helpEn,helpJa)=>({en,ja,helpEn,helpJa});
export const TEXT={
 note:row('Text and images come from the input sockets. Image tags are used for new T2I generation.','テキスト・画像は入力端子から接続します。画像はタグに変換して新規T2I生成します。','OFF uses manual_prompt unchanged. ON analyzes the connected image. Image identity is not guaranteed.','OFFはmanual_promptの原文、ONは接続画像の解析を使います。元画像との同一性は保証されません。'),
 advanced:row('Advanced settings','詳細設定','Open settings inside this panel. The node size stays unchanged; resize the node to see more.','ノードの寸法を変えず、このパネル内で設定を開きます。ノードを広げると表示領域も広がります。'),
 thresholds:row('Tag adoption scores (0–1)','タグ採用スコア（0～1）','Higher values keep fewer, more confident tags. Blank uses the selected model default.','値を上げると確度の高い少数のタグを採用します。空欄は選択モデルの既定値です。'),
 additions:row('Additional appearance tags by view group','ビュー別の外観追加タグ','Optional literal tags, separated by comma and space. They supplement automatic tags only for the listed views.','任意の外観タグをコンマ＋スペースで入力します。自動タグに加え、対応するビューだけへ渡します。'),
 general:row('Appearance score','外観スコア','Minimum score for general tags. Blank: PixAI 0.17, WD 0.35. Background and pose tags are still filtered.','一般タグの採用下限。空欄はPixAI 0.17、WD 0.35。背景・姿勢タグは別途除外します。'),
 character:row('Character-name score','キャラクター名スコア','Applies only when character names are enabled. A higher value accepts fewer names.','キャラクター名採用を有効にした場合の下限です。高いほど採用を絞ります。'),
 copyright:row('Series-name score','作品名スコア','Applies only when series names are enabled.','作品名採用を有効にした場合だけ使う下限です。'),
 style:row('Style candidate score','画風候補スコア','Controls candidate filtering for Review. Style tags are not automatically added to appearance.','Review候補の選別に使います。画風を外観へ自動追加する設定ではありません。'),
 meta:row('Metadata candidate score','メタ情報候補スコア','Controls Review candidate filtering. Metadata tags are excluded from automatic appearance.','Review候補の選別に使います。メタ情報は自動外観から除外します。'),
 rating:row('Rating candidate score','レーティング候補スコア','Controls Review candidate filtering. Ratings are excluded from automatic appearance.','Review候補の選別に使います。レーティングは自動外観から除外します。'),
 include_character:row('Include character names','キャラクター名を採用','Optional character labels in portrait/body prompts. Names may introduce familiar clothing or other traits. Default OFF.','顔・全身へキャラクター名を追加します。名前から既知の衣装などが混ざる場合があります。既定OFF。'),
 include_copyright:row('Include series names','作品名を採用','Optional series labels in portrait/body prompts. They may change appearance. Default OFF.','顔・全身へ作品名を追加します。外観が変わる場合があります。既定OFF。'),
 exclude:row('Exclude raw tags','除外するrawタグ','Exact raw names, for example blue_hair. Comma/newline separated. Manual input text is not filtered.','blue_hairなど解析のraw名を完全一致で除外します。コンマまたは改行で区切ります。手動入力文は変更しません。'),
 maximum:row('Maximum automatic tags','自動採用タグ数の上限','1–128 automatic appearance tags. Manual additions are stored separately.','自動外観タグの上限（1～128）です。手動追加は別に保持します。'),
 gpu:row('CUDA device index','CUDAデバイス番号','GPU index starting at 0. Used by auto/cuda; not CPU mode.','0から始まるGPU番号。auto／cudaで使い、CPUモードには影響しません。'),
 multiple:row('Allow multiple subjects','複数の被写体を許可','Default OFF. Enabling this can mix different people’s features into a sheet.','既定OFF。有効にすると複数人物の特徴が混ざる場合があります。'),
 subject:row('Subject count / type','被写体の人数・種類','Optional tags such as 1girl or 1boy, for portrait/body views only. This is not a general prompt field.','1girl、1boyなどを任意で追加します。顔・全身だけに適用し、衣装・手足へ渡しません。全体プロンプト欄ではありません。'),
 hair:row('Hair','髪','Hair tags for portraits and body views. Leave blank to use automatic tags.','顔・全身用の髪タグです。空欄なら自動解析結果を使います。'),
 face:row('Face','顔','Eye/face appearance for portraits and front/side body views. Excluded from rear views.','顔・目の外観タグ。顔と全身の正面・側面に使い、背面へは渡しません。'),
 body:row('Body','体','Body appearance for full-body views only; no framing instructions.','全身用の体の外観タグです。構図指示を書く欄ではありません。'),
 upper_outfit:row('Upper clothing','上半身の衣装','Upper garment tags for compatible portrait/body/clothing views.','対応する顔・全身・衣装ビュー用の上衣タグです。'),
 lower_outfit:row('Lower clothing','下半身の衣装','Lower garment tags for body and clothing views.','全身・衣装ビュー用の下衣タグです。'),
 hands:row('Hands / gloves','手・手袋','Hand or glove details for body/hand views; no character names.','全身・手ビュー用の手や手袋の外観タグです。人物名は不要です。'),
 feet:row('Feet / footwear','足・履物','Shoes, boots or socks for body/footwear views.','全身・履物ビュー用の靴・ブーツ・靴下などのタグです。'),
 head_accessories:row('Head accessories','頭の装飾','Head accessories for portrait/body views.','顔・全身用の頭の装飾タグです。'),
 body_accessories:row('Body accessories','体の装飾','Accessories for full-body views. Clothing construction belongs in upper/lower clothing.','全身用の装飾タグです。衣装の構造は上衣・下衣欄へ入力します。'),
 download:row('Download selected model','選択モデルをダウンロード','Download the selected pinned model now. Verified files are reused. Progress and destination appear below. No image is uploaded. Use this button inside the Tagger node.','選択中の固定版モデルを今すぐ取得します。検証済みファイルは再利用します。進捗と保存先は下に表示します。画像は送信しません。Taggerノード内で使用するボタンです。'),
 refresh:row('Refresh analysis / retry device','解析を更新・デバイスを再試行','Recheck files and retry inference on the next run. Does not queue generation.','次回実行でファイル検証と推論を再試行します。このボタンだけでは生成を開始しません。'),
 decisions:row('Last filtering details','直近のタグ選別結果','Kept: adopted automatic tags; added: your additions; excluded: removed; review: unclassified candidates.','keptは自動採用、addedは手動追加、excludedは除外、reviewは未分類候補です。'),
};
export const STATUS={en:{stale:'Settings changed — run to refresh results',idle:'Not run',running:'Analyzing…',manual:'Text input — analysis bypassed',failed:'Analysis failed',invalid:'Invalid saved Tagger settings',ime:'Finish IME composition before queueing.',numeric:'Invalid Tagger numeric setting.',cached:'cached'},ja:{stale:'設定を変更しました。次回実行で更新します',idle:'未実行',running:'解析中…',manual:'テキスト入力：画像解析なし',failed:'画像解析に失敗しました',invalid:'保存されたTagger設定が不正です',ime:'日本語入力を確定してから実行してください。',numeric:'Taggerの数値設定が不正です。',cached:'キャッシュ使用'}};
export const DOWNLOAD={en:{downloaded:'Downloaded',modified:'File modified',unknown:'Not recorded (existing files)',checking:'Checking model',missing:'Not installed',downloading:'Downloading',verifying:'Verifying files',ready:'Model ready',error:'Download failed — retry',busy:'Another download is running',unavailable:'Model status unavailable',path:'Model storage folder. Weights are outside custom_nodes.',restart:'Restart ComfyUI_test to load the updated model service.'},ja:{downloaded:'取得日時',modified:'ファイル更新日時',unknown:'記録なし（既存ファイル）',checking:'モデルを確認中',missing:'未導入',downloading:'ダウンロード中',verifying:'ファイルを検証中',ready:'モデル準備完了',error:'取得失敗・再試行',busy:'別のモデルを取得中',unavailable:'モデル状態を取得できません',path:'重みの保存先です。custom_nodesの外に保存します。',restart:'更新したモデル取得機能を使うにはComfyUI_testを再起動してください。'}};
export function words(key,locale='en'){const t=TEXT[key];return {label:t[locale==='ja'?'ja':'en'],help:t[locale==='ja'?'helpJa':'helpEn']};}
