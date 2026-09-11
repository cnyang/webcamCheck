from webcamcheck.cli import build_parser


def test_run_defaults() -> None:
    args = build_parser().parse_args(["run"])
    # 預設照名稱抓,不寫死編號:iPhone 接續互通攝影機插拔會讓編號位移
    assert args.camera_name == "Brio 100"
    assert args.camera_id is None
    assert args.neck_tolerance == 8.0
    assert args.interval == 2.0
    assert args.sustain == 8.0
    assert args.cooldown == 120.0
    assert args.facing_ratio == 0.7
    assert args.near_ratio == 1.12
    assert args.no_check_distance is False, "距離偵測預設開啟"
    assert args.check_tilt is False, "肩膀傾斜偵測預設要關閉,避免轉身誤報"
    assert args.func.__name__ == "_cmd_run"


def test_sound_defaults_on() -> None:
    args = build_parser().parse_args(["run"])
    assert args.sound == "Sosumi"
    assert args.no_sound is False


def test_sound_can_be_disabled() -> None:
    assert build_parser().parse_args(["run", "--no-sound"]).no_sound is True


def test_sound_can_be_chosen() -> None:
    assert build_parser().parse_args(["run", "--sound", "Hero"]).sound == "Hero"


def test_check_tilt_is_opt_in() -> None:
    args = build_parser().parse_args(["run", "--check-tilt"])
    assert args.check_tilt is True


def test_calibrate_defaults() -> None:
    args = build_parser().parse_args(["calibrate"])
    assert args.camera_name == "Brio 100"
    assert args.camera_id is None
    assert args.seconds == 5.0
    assert args.func.__name__ == "_cmd_calibrate"


def test_view_subcommand_exists() -> None:
    args = build_parser().parse_args(["view"])
    assert args.camera_name == "Brio 100"
    assert args.func.__name__ == "_cmd_view"


def test_camera_id_can_be_given() -> None:
    args = build_parser().parse_args(["run", "--camera-id", "0x3123000046d094c"])
    assert args.camera_id == "0x3123000046d094c"


def test_list_cameras_defaults() -> None:
    args = build_parser().parse_args(["list-cameras"])
    assert args.func.__name__ == "_cmd_list_cameras"


def test_debug_subcommand_exists() -> None:
    args = build_parser().parse_args(["debug", "--camera-id", "0xabc"])
    assert args.camera_id == "0xabc"
    assert args.facing_ratio == 0.7
    assert args.func.__name__ == "_cmd_debug"


def test_run_accepts_overrides() -> None:
    args = build_parser().parse_args(
        ["run", "--camera-id", "0xabc", "--sustain", "10", "--cooldown", "30", "--facing-ratio", "0.55"]
    )
    assert args.camera_id == "0xabc"
    assert args.sustain == 10.0
    assert args.cooldown == 30.0
    assert args.facing_ratio == 0.55


def test_near_ratio_can_be_overridden() -> None:
    args = build_parser().parse_args(["run", "--near-ratio", "1.2"])
    assert args.near_ratio == 1.2


def test_distance_check_can_be_disabled() -> None:
    assert build_parser().parse_args(["run", "--no-check-distance"]).no_check_distance is True


def test_debug_has_distance_args() -> None:
    args = build_parser().parse_args(["debug"])
    assert args.near_ratio == 1.12


def test_menubar_program_args_carry_distance_settings() -> None:
    from webcamcheck.cli import menubar_program_args

    args = build_parser().parse_args(["install-startup", "--near-ratio", "1.2"])
    command = menubar_program_args(args)
    assert "--near-ratio" in command
    assert command[command.index("--near-ratio") + 1] == "1.2"


def test_menubar_program_args_carry_distance_opt_out() -> None:
    from webcamcheck.cli import menubar_program_args

    args = build_parser().parse_args(["install-startup", "--no-check-distance"])
    assert "--no-check-distance" in menubar_program_args(args)
