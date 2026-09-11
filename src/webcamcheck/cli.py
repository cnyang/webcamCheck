"""命令列介面:list-cameras / calibrate / run / debug / view 五個子指令。"""

from __future__ import annotations

import argparse
import logging
import time

from webcamcheck import autostart, calibration, config, controller, menubar, monitor, overlay
from webcamcheck.camera import Camera
from webcamcheck.devices import DEFAULT_CAMERA_NAME, list_devices
from webcamcheck.landmarks import sample_from_landmarks
from webcamcheck.notifier import DEFAULT_SOUND, available_sounds
from webcamcheck.pose_estimator import PoseEstimator
from webcamcheck.posture import UNKNOWN_VERDICT, Baseline, PostureStatus, classify

logger = logging.getLogger(__name__)

DEFAULT_NECK_TOLERANCE = 8.0
DEFAULT_TILT_TOLERANCE = 15.0
DEFAULT_FACING_RATIO = 0.7
# 實測:正常坐著肩寬在基準的 99~107%,上身前傾是 109~117%。
DEFAULT_NEAR_RATIO = config.DEFAULT_NEAR_RATIO


def _sound_name(args: argparse.Namespace) -> str | None:
    return None if args.no_sound else args.sound


def _check_distance(args: argparse.Namespace) -> bool:
    return not args.no_check_distance


def _open_camera(args: argparse.Namespace) -> Camera:
    """照名稱或 uniqueID 開,不用編號 — OpenCV 的編號順序和 AVFoundation 對不上。"""
    return Camera(name=args.camera_name, unique_id=args.camera_id)


def _cmd_list_cameras(_args: argparse.Namespace) -> None:
    devices = list_devices()
    if not devices:
        print("沒偵測到任何攝影機。")
        return
    for device in devices:
        print(f"{device.name}  (uniqueID={device.unique_id})")
    print(f"預設會照名稱抓「{DEFAULT_CAMERA_NAME}」。要精準指定就用 --camera-id。")


def _cmd_calibrate(args: argparse.Namespace) -> None:
    with _open_camera(args) as camera:
        estimator = PoseEstimator()
        try:
            print(f"坐正,維持 {args.seconds:.0f} 秒進行校準…")
            baseline = calibration.calibrate(camera, estimator, duration_seconds=args.seconds)
        finally:
            estimator.close()
    config.save_baseline(baseline)
    print(f"校準完成:neck={baseline.neck_angle_deg:.1f}° tilt={baseline.shoulder_tilt_deg:.1f}°")
    print(f"肩寬基準={baseline.shoulder_width:.3f}(轉身時肩寬會變小,用來判斷你是不是轉去用另一台電腦)")
    print("同一個肩寬也用來判斷距離:上身往前傾時肩膀靠近鏡頭,肩寬會變大。")
    print(f"已存到 {config.CONFIG_PATH}")


def _require_baseline() -> Baseline:
    baseline = config.load_baseline()
    if baseline is None:
        print("尚未校準(或設定檔已損毀),先執行:webcamcheck calibrate")
        raise SystemExit(1)
    return baseline


def _cmd_run(args: argparse.Namespace) -> None:
    monitor.run(
        camera=_open_camera(args),
        baseline=_require_baseline(),
        neck_tolerance_deg=args.neck_tolerance,
        tilt_tolerance_deg=args.tilt_tolerance,
        check_interval_seconds=args.interval,
        sustain_seconds=args.sustain,
        cooldown_seconds=args.cooldown,
        facing_ratio=args.facing_ratio,
        check_tilt=args.check_tilt,
        near_ratio=args.near_ratio,
        check_distance=_check_distance(args),
        sound_name=_sound_name(args),
    )


def _cmd_debug(args: argparse.Namespace) -> None:
    """即時印出目前的角度和判定,讓你可以實際轉身/駝背,看數字決定門檻要設多少。"""
    baseline = _require_baseline()
    label = {PostureStatus.GOOD: "良好", PostureStatus.BAD: "歪掉", PostureStatus.UNKNOWN: "不判斷"}
    print(f"基準:neck={baseline.neck_angle_deg:.1f}°  肩寬={baseline.shoulder_width:.3f}")
    print("轉去用另一台電腦、離開座位、故意駝背、上身往前傾各試幾秒,看下面數字怎麼變。Ctrl+C 結束。\n")
    with _open_camera(args) as camera:
        estimator = PoseEstimator()
        try:
            while True:
                frame = camera.read()
                sample = estimator.detect(frame) if frame is not None else None
                if sample is None:
                    # flush:輸出被導到檔案或 pipe 時是 block buffering,不 flush 就看不到即時數值
                    print("偵測不到人(離開座位或鏡頭拍不到肩膀) -> 不判斷", flush=True)
                else:
                    verdict = classify(
                        sample,
                        baseline,
                        neck_tolerance_deg=args.neck_tolerance,
                        tilt_tolerance_deg=args.tilt_tolerance,
                        facing_ratio=args.facing_ratio,
                        check_tilt=args.check_tilt,
                        near_ratio=args.near_ratio,
                        check_distance=_check_distance(args),
                    )
                    ratio = sample.shoulder_width / baseline.shoulder_width
                    print(
                        f"neck={sample.neck_angle_deg:6.1f}°  "
                        f"tilt={sample.shoulder_tilt_deg:6.1f}°  "
                        f"肩寬={sample.shoulder_width:.3f}(基準的 {ratio:4.0%})  "
                        f"-> {label[verdict.status]}{'(太近)' if verdict.too_close else ''}",
                        flush=True,
                    )
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n結束。")
        finally:
            estimator.close()


def _cmd_view(args: argparse.Namespace) -> None:
    """開一個視窗,即時畫出耳朵/肩膀/手肘的連線和角度。按 q 或 Esc 關閉。"""
    import cv2

    baseline = _require_baseline()
    window = "webcamcheck"
    with _open_camera(args) as camera:
        estimator = PoseEstimator()
        try:
            while True:
                frame = camera.read()
                if frame is None:
                    continue
                height, width = frame.shape[:2]
                landmarks = estimator.detect_landmarks(frame)
                if landmarks is None:
                    sample, verdict = None, UNKNOWN_VERDICT
                else:
                    sample = sample_from_landmarks(landmarks, aspect_ratio=width / height)
                    verdict = (
                        UNKNOWN_VERDICT
                        if sample is None
                        else classify(
                            sample,
                            baseline,
                            neck_tolerance_deg=args.neck_tolerance,
                            tilt_tolerance_deg=args.tilt_tolerance,
                            facing_ratio=args.facing_ratio,
                            check_tilt=args.check_tilt,
                            near_ratio=args.near_ratio,
                            check_distance=_check_distance(args),
                        )
                    )
                canvas = overlay.draw_posture(frame, landmarks, sample, verdict, baseline)
                cv2.imshow(window, canvas)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            estimator.close()
            cv2.destroyAllWindows()


def _menubar_settings(args: argparse.Namespace) -> controller.MenuBarSettings:
    return controller.MenuBarSettings(
        camera_name=args.camera_name,
        camera_id=args.camera_id,
        neck_tolerance_deg=args.neck_tolerance,
        tilt_tolerance_deg=args.tilt_tolerance,
        facing_ratio=args.facing_ratio,
        check_tilt=args.check_tilt,
        near_ratio=args.near_ratio,
        check_distance=_check_distance(args),
        interval_seconds=args.interval,
        sustain_seconds=args.sustain,
        cooldown_seconds=args.cooldown,
        sound_name=_sound_name(args),
    )


def _cmd_menubar(args: argparse.Namespace) -> None:
    menubar.run(_menubar_settings(args))


def menubar_program_args(args: argparse.Namespace) -> list[str]:
    """開機自動啟動時要執行的完整指令。把當下的設定值一起寫進去,登入後行為才會一致。"""
    command = [str(autostart.executable_path()), "menubar", "--camera-name", args.camera_name]
    if args.camera_id is not None:
        command += ["--camera-id", args.camera_id]
    command += [
        "--neck-tolerance",
        str(args.neck_tolerance),
        "--facing-ratio",
        str(args.facing_ratio),
        "--near-ratio",
        str(args.near_ratio),
        "--interval",
        str(args.interval),
        "--sustain",
        str(args.sustain),
        "--cooldown",
        str(args.cooldown),
    ]
    if args.check_tilt:
        command.append("--check-tilt")
    if args.no_check_distance:
        command.append("--no-check-distance")
    if args.no_sound:
        command.append("--no-sound")
    else:
        command += ["--sound", args.sound]
    return command


def _cmd_install_startup(args: argparse.Namespace) -> None:
    plist_path = autostart.install(menubar_program_args(args))
    print(f"已設定登入時自動啟動:{plist_path}")
    print(f"記錄檔:{autostart.LOG_PATH}")
    print("選單列現在應該已經出現圖示。")
    print("注意:launchd 自動啟動的攝影機權限,和從終端機執行是分開算的。")
    print(f"圖示如果顯示 ⚠️,看一下 {autostart.LOG_PATH},多半是要在「系統設定 > 隱私權與安全性 > 相機」再允許一次。")


def _cmd_uninstall_startup(_args: argparse.Namespace) -> None:
    if autostart.uninstall():
        print("已取消登入自動啟動。")
    else:
        print("本來就沒有設定自動啟動。")


def _add_camera_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--camera-name",
        default=DEFAULT_CAMERA_NAME,
        help=f"照名稱找攝影機,不受編號位移影響(預設「{DEFAULT_CAMERA_NAME}」)",
    )
    parser.add_argument(
        "--camera-id",
        default=None,
        help="用 uniqueID 精準指定攝影機,會蓋過 --camera-name(用 list-cameras 查)",
    )


def _add_detection_args(parser: argparse.ArgumentParser) -> None:
    _add_camera_args(parser)
    parser.add_argument(
        "--neck-tolerance",
        type=float,
        default=DEFAULT_NECK_TOLERANCE,
        help=f"頸部角度容許值,超過基準多少度算歪(預設 {DEFAULT_NECK_TOLERANCE:.0f})",
    )
    parser.add_argument(
        "--tilt-tolerance",
        type=float,
        default=DEFAULT_TILT_TOLERANCE,
        help=f"肩膀傾斜容許值,只有加了 --check-tilt 才有作用(預設 {DEFAULT_TILT_TOLERANCE:.0f})",
    )
    parser.add_argument(
        "--check-tilt",
        action="store_true",
        help="啟用肩膀傾斜偵測。單顆前視鏡頭分不出轉身和真的歪斜,預設關閉以免一直誤報。",
    )
    parser.add_argument(
        "--facing-ratio",
        type=float,
        default=DEFAULT_FACING_RATIO,
        help=f"肩寬掉到基準的幾成以下就當作你轉身了,不判斷姿勢(預設 {DEFAULT_FACING_RATIO})",
    )
    parser.add_argument(
        "--near-ratio",
        type=float,
        default=DEFAULT_NEAR_RATIO,
        help=f"肩寬超過校準值的幾倍算上身前傾坐太近,越小越嚴格(預設 {DEFAULT_NEAR_RATIO})",
    )
    parser.add_argument(
        "--no-check-distance",
        action="store_true",
        help="關掉「離螢幕太近」偵測,只看姿勢角度",
    )
    parser.add_argument("--interval", type=float, default=2.0, help="每幾秒偵測一次(預設 2)")


def _add_monitor_args(parser: argparse.ArgumentParser) -> None:
    """會實際發通知的模式(run / menubar / install-startup)共用的參數。"""
    _add_detection_args(parser)
    parser.add_argument("--sustain", type=float, default=8.0, help="姿勢歪掉要持續幾秒才通知(預設 8)")
    parser.add_argument(
        "--sound",
        default=DEFAULT_SOUND,
        help=f"提醒時播放的音效(預設 {DEFAULT_SOUND};可用:{'、'.join(available_sounds())})",
    )
    parser.add_argument("--no-sound", action="store_true", help="只跳通知,不出聲")
    parser.add_argument("--cooldown", type=float, default=120.0, help="通知後至少間隔幾秒才會再通知(預設 120)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="webcamcheck", description="坐姿監控:偵測駝背並跳系統通知提醒")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-cameras", help="列出接上的攝影機名稱與 uniqueID")
    p_list.set_defaults(func=_cmd_list_cameras)

    p_cal = sub.add_parser("calibrate", help="坐正後錄製姿勢基準值")
    _add_camera_args(p_cal)
    p_cal.add_argument("--seconds", type=float, default=5.0)
    p_cal.set_defaults(func=_cmd_calibrate)

    p_run = sub.add_parser("run", help="開始監控,姿勢歪掉持續夠久會跳系統通知")
    _add_monitor_args(p_run)
    p_run.set_defaults(func=_cmd_run)

    p_debug = sub.add_parser("debug", help="即時顯示角度與判定,用來調門檻")
    _add_detection_args(p_debug)
    p_debug.set_defaults(func=_cmd_debug)

    p_view = sub.add_parser("view", help="開視窗即時畫出耳朵/肩膀/手肘的連線與角度")
    _add_detection_args(p_view)
    p_view.set_defaults(func=_cmd_view)

    p_menu = sub.add_parser("menubar", help="常駐在選單列,有圖示和選單可以控制")
    _add_monitor_args(p_menu)
    p_menu.set_defaults(func=_cmd_menubar)

    p_install = sub.add_parser("install-startup", help="設定登入時自動啟動選單列程式")
    _add_monitor_args(p_install)
    p_install.set_defaults(func=_cmd_install_startup)

    p_uninstall = sub.add_parser("uninstall-startup", help="取消登入自動啟動")
    p_uninstall.set_defaults(func=_cmd_uninstall_startup)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        # 開不了鏡頭、校準抓不到人這類可預期的失敗,印訊息就好,不要丟一整串 traceback 給使用者。
        print(exc)
        raise SystemExit(1) from exc
