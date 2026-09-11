# webcamcheck

用 Brio 100 webcam 偵測坐姿,駝背/歪頭持續太久就跳 macOS 系統通知。

## 原理

用 mediapipe 的姿勢偵測(舊版 `mp.solutions.pose`,新版 Tasks API 在這台機器的 macOS 上
會因為 Metal GPU calculator service 崩潰,詳見 `src/webcamcheck/pose_estimator.py` 的註解)
抓出耳朵和肩膀的關鍵點,算兩個角度:

- **頸部角度**:耳朵-肩膀連線與垂直軸的夾角。角度越大代表頭越往前垂(對應書上「耳朵和肩膀的連線呈筆直」)。
  頭垂到肩膀線以下(趴在桌上)時角度會超過 90 度繼續變大,不會折返成小角度被誤判為坐姿良好。
- **肩寬**:兩肩在畫面上的水平距離,用來判斷「你有沒有正對鏡頭」。轉身去用旁邊那台電腦時,
  兩肩投影會被壓扁、肩寬明顯變小;低頭駝背則不會,所以不會把該提醒的姿勢誤放過。
  **肩寬同時也是距離指標**,因為兩種情況讓它往相反方向動:轉身讓它變小,上身前傾讓它變大
  (肩膀靠近鏡頭,投影變大)。實測(基準 = 坐正校準值):

  | 姿勢 | 肩寬 | neck 角度 |
  |---|---|---|
  | 正常坐著 | 99~107% | 14~15° |
  | 背打直、上身往前傾 | 109~117% | 20~23° |
  | 駝背 | 111~119% | 27~48° |
  | 轉身去用另一台電腦 | 約 27% | — |

  同階段內肩寬抖動只有 ±1.5%,所以 `--near-ratio` 預設 1.12 有 5% 緩衝,坐著不動不會誤報。
  前傾和駝背在肩寬上分不開,但 neck 角度分得開,所以駝背成立時就不另外報「太近」 — 該修的是駝背。

  **量距離為什麼不用兩耳距離**:直覺上頭是剛體應該更可靠,實測卻相反 — 上身前傾時兩耳距離
  從基準的 104% 掉到 79~92%(方向完全錯),駝背時在 76~125% 之間亂跳。BlazePose 的耳朵點
  在近距離或頭有俯仰角時會塌向臉中心。這條路試過了,別再走一次。

- **肩膀傾斜角**:兩肩連線與水平軸的夾角。**預設不啟用** — 單顆前視鏡頭分不出「轉身」和「真的左右歪」,
  實測挺著坐是 18.6°、駝背是 16.5°,幾乎沒有鑑別力,開著只會一直誤報。真的想用再加 `--check-tilt`。

mediapipe 的座標是 x 除以影像寬、y 除以影像高,兩者基準不同,所以算角度前會先用畫面長寬比修正,
否則 16:9 的畫面會把水平位移放大 1.78 倍,「8 度」就不是真的 8 度。

先在坐正的狀態下校準,記錄基準值(每個人的脖子長短、鏡頭擺放角度都不同,用絕對角度會不準)。
之後監控時角度超出基準加容許值,而且持續超過設定秒數,才跳系統通知。

姿勢對但上身往前傾、離螢幕太近一樣會提醒(`肩寬 > 基準 × --near-ratio`,預設 1.12 倍)。
實測背打直前傾時 neck 只有 20~23°,還在容許值內,所以只有肩寬抓得到這個姿勢。
距離判定排在「有沒有正對鏡頭」的閘門後面,轉身時肩寬會縮,不該在那時候判距離。

**什麼時候不會吵你**:

- 轉身去用另一台電腦(肩寬掉到基準的 `--facing-ratio` 以下)
- 離開座位、鏡頭拍不到肩膀
- 這兩種情況都會讓「歪掉持續時間」歸零,所以回座後要重新累積滿 `--sustain` 秒才會提醒,
  不會一坐下就被離開前的計時秒殺。

## 使用方式

```bash
# 1.(選用)確認抓到哪些攝影機。預設會自動照名稱找 Brio 100,通常這步可以跳過
uv run webcamcheck list-cameras

# 2. 坐正,校準基準值(預設錄 5 秒取平均)
uv run webcamcheck calibrate

# 3. 開視窗看骨架:耳朵/肩膀/手肘的連線和角度。按 q 或 Esc 關掉
uv run webcamcheck view

# 4. 只想看數字不想開視窗,用 debug(轉身、離開座位、故意駝背各試幾秒)
uv run webcamcheck debug

# 5. 開始監控,姿勢歪掉持續夠久會跳系統通知
uv run webcamcheck run

# 6. 或是常駐在選單列(有圖示和選單),並設定登入時自動啟動
uv run webcamcheck menubar
uv run webcamcheck install-startup
```

## 選單列常駐

`webcamcheck menubar` 會在選單列放一個圖示:

| 圖示 | 意思 |
|---|---|
| 🟢 | 坐姿良好 |
| 🔴 | 姿勢歪了 |
| ⚪ | 不判斷(離開座位或轉身) |
| ⏸ | 已暫停 |
| ⏳ | 啟動中或校準中 |
| ⚠️ | 出問題了,點開選單看訊息 |

選單裡有:目前狀態、暫停/繼續監控、重新校準、開啟即時畫面,以及四個判斷標準的子選單:

| 子選單 | 檔位 | 意思 |
|---|---|---|
| 靈敏度 | 嚴格 5° / 標準 8° / 寬鬆 12° / 很寬鬆 16° | 頸部角度超過基準多少度算歪 |
| 提醒前等待 | 3 / 5 / 8 / 15 / 30 秒 | 壞姿勢要持續多久才提醒 |
| 轉身判定 | 嚴格 80% / 標準 70% / 寬鬆 55% | 肩寬掉到基準的幾成算你轉身了 |
| 距離判定 | 嚴格 108% / 標準 112% / 寬鬆 120% | 肩寬漲到基準的幾倍算上身前傾太近 |

目前選中的那一檔會打勾。改完**立刻生效並存到 `~/.webcamcheck/tuning.json`**,下次登入沿用 —
存過的標準會蓋過 plist 裡的啟動參數,否則每次登入都會被舊值蓋回去。

判斷標準和校準基準分兩個檔案存:基準是動過鏡頭才要重做的,標準是隨時想調就調的,
混在一起的話「重新校準」會不小心把調好的標準蓋掉。

改標準的當下會把「歪了幾秒」的計時歸零 — 否則放寬門檻的瞬間,先前累積的秒數會立刻噴一次通知。

「開啟即時畫面」是另開一個 process 跑 `view`,因為 OpenCV 視窗需要自己的主執行緒,
塞進 rumps 的 runloop 會打架。校準則是丟到背景執行緒,不會卡住選單。

Brio 100 沒插上時不會直接放棄,圖示顯示 ⚠️ 並持續重試,插上就會自己接起來。

## 開機自動啟動

```bash
uv run webcamcheck install-startup     # 安裝(會把當下的參數一起寫進去)
uv run webcamcheck uninstall-startup   # 移除
```

裝的是 LaunchAgent(`~/Library/LaunchAgents/com.cnyang.webcamcheck.plist`),不是 LaunchDaemon —
選單列圖示必須跑在使用者的圖形介面 session 裡,daemon 沒有 GUI session,圖示不會出現。
`KeepAlive` 設 `false`,所以你從選單按「結束」之後不會又被 launchd 拉起來。

記錄檔在 `~/Library/Logs/webcamcheck.log`。

### ⚠ 攝影機權限要授權兩次

**實測過**:從終端機執行時 AVFoundation 回報 `authorized`,但同一支程式被 launchd 拉起來時是:

```
OpenCV: not authorized to capture video (status 0), requesting...
```

macOS 的 TCC 權限是綁「負責的程式」,終端機啟動和 launchd 啟動算兩回事。所以第一次
`install-startup` 之後,要到「系統設定 > 隱私權與安全性 > 相機」再允許一次。
權限沒開時錯誤訊息會直接講權限,不會誤導成找不到裝置。

### 提醒方式

姿勢歪掉持續夠久時,會**同時**出聲和跳系統通知。

聲音是自己用 `afplay` 播,不是交給通知的 `sound name` — 通知的聲音會被「通知設定」或專注模式吃掉,
常常看得到卻聽不到,而提醒坐姿本來就需要你聽得見。`afplay` 用 `Popen` 丟出去不等它播完,
因為播一次要兩秒多,擋在監控迴圈裡會拖慢偵測。

### view 視窗

- 綠/紅/灰 = 姿勢良好 / 該調整了 / 不判斷(離開座位或轉身)
- 綠線:兩耳到肩膀中點,也就是實際用來算 neck 角度的線
- 淺藍直線:垂直參考線,耳朵越靠近這條線代表越接近書上說的「耳朵和肩膀的連線呈筆直」
- 橘線:肩膀到手肘,標的是「耳-肩-肘」在肩膀處張開的角度
- 左上角顯示 neck 角度與基準差多少、肩膀傾斜、目前肩寬是基準的幾 %
  (前傾太近時多一行 `TOO CLOSE - sit back`)

視窗文字一律英數,因為 OpenCV 的 `putText` 畫不出中文(會變成方塊)。

坐太近時手肘會掉出取景範圍(實測你那張照片手肘落在 y=1291,畫面只有 1080 高),
這時左上角會顯示 `elbows out of frame - sit back or tilt camera down`。想看到手肘就把 Brio 100
往後移或往下壓一點。

`run` 的容許值/秒數都可調(看 `uv run webcamcheck run --help`):

- `--neck-tolerance`(預設 8 度):頸部角度超過基準多少度算歪。
- `--facing-ratio`(預設 0.7):肩寬掉到基準的幾成以下就當作你轉身了,暫停判斷。
- `--near-ratio`(預設 1.12):肩寬漲到基準的幾倍算上身前傾坐太近,越小越嚴格。
- `--no-check-distance`:關掉距離偵測,只看姿勢角度。
- `--sustain`(預設 8 秒):壞姿勢要持續多久才通知,避免彎腰撿東西也跳通知。
- `--cooldown`(預設 120 秒):同一段壞姿勢期間,通知的最短間隔,避免洗版。
  一旦坐正或離開座位就重置,所以你改正之後再度駝背會是全新一段,照樣會提醒。
- `--interval`(預設 2 秒):多久偵測一次。
- `--sound`(預設 `Sosumi`):提醒音效,可用 `/System/Library/Sounds` 裡的任一個
  (Basso、Blow、Bottle、Frog、Funk、Glass、Hero、Morse、Ping、Pop、Purr、Sosumi、Submarine、Tink)。
- `--no-sound`:只跳通知不出聲。
- `--check-tilt`:啟用肩膀傾斜偵測(預設關閉,理由見上面「原理」)。

`--facing-ratio` 的預設值 0.7 是估的,務必用 `debug` 實際轉身去看肩寬掉到幾 %,再回頭調。
太高會在你稍微側身時就停止監控,太低則轉身時仍會誤報。

`--near-ratio` 同理:用 `debug` 前傾到你覺得「這樣太近了」的位置,看肩寬變成基準的幾 %,
取「正常坐著的上限」和「前傾的下限」中間值。校準姿勢會直接決定這個基準,所以校準時要坐在
你希望維持的那個距離。

### 攝影機是用名稱指定的,沒有「編號」這回事

擷取層走 AVFoundation(pyobjc),裝置直接用 uniqueID 指定,所以完全沒有序號位移的問題。
預設照名稱找(`--camera-name`,預設 `Brio 100`),要精準指定就 `--camera-id`(用 `list-cameras` 查):

```
$ uv run webcamcheck list-cameras
Brio 100  (uniqueID=0x3123000046d094c)
cnyangPhone16 Camera  (uniqueID=0EFC59B2-...)
```

**為什麼不用 `cv2.VideoCapture(index)`**:OpenCV 的裝置順序和 AVFoundation 對不上。
Brio 100 和 iPhone 接續互通攝影機同時接著時實測:

| 來源 | index 0 | index 1 |
|---|---|---|
| AVFoundation `devicesWithMediaType` | Brio 100 | iPhone |
| OpenCV `VideoCapture` | **iPhone** | **Brio 100** |

兩邊是反的。「用 AVFoundation 查名稱、再把序號交給 OpenCV」會開到錯的鏡頭 —
只有一台鏡頭時剛好會過,插上 iPhone 就變成監控手機。所以擷取整個改走 AVFoundation。

OpenCV 仍然有用到,但只負責影像處理(色彩轉換、疊圖、`view` 視窗),不再碰裝置選擇。

找不到指定的鏡頭時會列出現在接了什麼:

```
找不到名稱包含「Brio 100」的攝影機。目前接上的是:cnyangPhone16 Camera
```

> AVFoundation 的預設 FOV 和 OpenCV 不一樣,所以從舊版升上來要**重新 `calibrate`**。

覺得太敏感/太遲鈍就調 `--sustain` 和 `--neck-tolerance`;換位置或動過鏡頭角度後記得重新 `calibrate`
(基準值存在 `~/.webcamcheck/config.json`;檔案損毀或格式對不上會自動當成未校準,提示你重跑)。

## 開發

```bash
uv sync                                    # 裝依賴(含 dev 工具)
uv run pytest --cov --cov-report=term-missing   # 跑測試 + 覆蓋率
uv run ruff check src tests                # lint
uv run black src tests && uv run isort src tests   # 格式化
uv run mypy src tests                      # 型別檢查(strict)
uv run bandit -r src                       # 安全掃描
```

純邏輯(角度計算、姿勢判斷、通知節流狀態機)在 `geometry.py` / `posture.py` / `state.py`,
不碰攝影機或 mediapipe,單元測試涵蓋率 100%。攝影機、mediapipe、系統通知這些 I/O 邊界用假物件
(fake camera/estimator)測試 glue 邏輯,`cli.py` 的指令本體與 `monitor.run()` 的無窮迴圈本身
留給手動測試(已用 Brio 100 實測過 calibrate/run 都正常)。
