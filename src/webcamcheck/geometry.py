"""純幾何計算:只吃座標,不碰攝影機或 mediapipe,方便單元測試。

座標是 mediapipe 的正規化座標:x 除以影像寬、y 除以影像高。兩者基準不同,所以算角度前
一定要把 x 乘上 aspect_ratio(寬/高)還原成同一個尺度,否則 16:9 的畫面會把水平位移
放大 1.78 倍,算出來的「度數」不是真的度數。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def ear_shoulder_angle(ear: Point, shoulder: Point, aspect_ratio: float = 1.0) -> float:
    """耳朵-肩膀連線與垂直軸的夾角(度),範圍 0~180。

    0 度 = 耳朵正好在肩膀正上方(書上說的「耳朵和肩膀的連線呈筆直」),角度越大代表頭越往前垂。
    影像座標的 y 是往下增長的,所以「耳朵在肩膀上方」時 dy 為正。這裡刻意用 atan2 保留正負號:
    一旦頭垂到肩膀線以下(趴在桌上),角度會繼續往 90 度以上長,而不是折返回 0 度被誤判成坐姿良好。
    """
    dx = abs(ear.x - shoulder.x) * aspect_ratio
    dy = shoulder.y - ear.y
    return math.degrees(math.atan2(dx, dy))


def shoulder_tilt_angle(left_shoulder: Point, right_shoulder: Point, aspect_ratio: float = 1.0) -> float:
    """兩肩連線與水平軸的夾角(度)。0 度表示肩膀齊平;角度越大代表左右歪斜越嚴重。"""
    dx = abs(left_shoulder.x - right_shoulder.x) * aspect_ratio
    dy = abs(left_shoulder.y - right_shoulder.y)
    if dx == 0:
        return 90.0
    return math.degrees(math.atan(dy / dx))


def angle_at_vertex(vertex: Point, first: Point, second: Point, aspect_ratio: float = 1.0) -> float:
    """以 vertex 為頂點,vertex->first 和 vertex->second 兩條線的夾角(度),範圍 0~180。
    用來看「耳-肩-肘」在肩膀處張開多少。"""
    ax = (first.x - vertex.x) * aspect_ratio
    ay = first.y - vertex.y
    bx = (second.x - vertex.x) * aspect_ratio
    by = second.y - vertex.y
    cross = ax * by - ay * bx
    dot = ax * bx + ay * by
    return math.degrees(math.atan2(abs(cross), dot))


def shoulder_width(left_shoulder: Point, right_shoulder: Point, aspect_ratio: float = 1.0) -> float:
    """兩肩在畫面上的水平距離。同一個值撐兩個判定,因為兩種情況讓它往相反方向動:

    - **轉身**面向側邊時兩肩投影被壓扁,這個值明顯變小(實測轉身約基準的 27%)。
    - **上身前傾**時肩膀靠近鏡頭,這個值變大(實測正常 99~107%、前傾 109~117%)。

    量距離刻意不用兩耳距離:實測前傾時它反而從 104% 掉到 79~92%,駝背時在 76~125% 之間亂跳。
    BlazePose 的耳朵點在近距離或頭有俯仰角時會塌向臉中心,方向是錯的。
    """
    return abs(left_shoulder.x - right_shoulder.x) * aspect_ratio
