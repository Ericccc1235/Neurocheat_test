"""
NeuroCheat 3D 第一人稱教室與書桌抽屜建模引擎 (Classroom 3D Perspective Engine)
實作內容：
1. 滑鼠控制第一人稱視角 (Yaw 左右轉頭看旁邊其他學生與窗戶、Pitch 上下抬頭看黑板奶龍 / 低頭看書桌考卷與抽屜小抄)
2. 3D 教室空間建模：立體地板磁磚、左右牆面與窗戶、天花板燈具、黑板、講台、蜂鳴器
3. 旁邊的其他學生 (3D 鄰座考生建模：左右鄰座、前排左右與正前方同學，具備寫考卷、抓頭、轉頭動態)
4. 玩家書桌與抽屜建模：
   - 玩家坐在書桌前，考卷平鋪在書桌桌面上 (隨 3D 視角透視投影，可直接點擊桌面考卷作答)
   - 小抄藏在書桌下方的立體抽屜裡
   - 打開小抄時，玩家會伸手拉開抽屜並展開抽屜裡的小抄；收起時手會將小抄合上並推回抽屜
"""

import math
import pygame


class Camera3D:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        # 玩家坐在書桌前的眼睛 3D 座標 (單位: 公尺)
        # x=0 為教室中央座位, y=1.34 為坐姿眼睛高度, z=-0.42 為坐在椅子上的位置
        self.pos = [0.0, 1.34, -0.42]
        # 視角角度 (弧度):
        # yaw > 0 為向右轉頭, yaw < 0 為向左轉頭
        # pitch > 0 為抬頭看黑板, pitch < 0 為低頭看書桌考卷與抽屜
        self.yaw = 0.0
        self.pitch = -0.24
        self.target_yaw = 0.0
        self.target_pitch = -0.24
        self.fov_scale = 680.0

    def update_from_mouse(self, mouse_pos, dt, hud_rect=None):
        """根據滑鼠位置平滑控制玩家在座位上的第一人稱視角"""
        mx, my = mouse_pos
        view_w = self.width - 385  # 左側 3D 視窗寬度

        if hud_rect and hud_rect.collidepoint(mx, my):
            # 滑鼠在右側儀表板操作時，保持面向正前方書桌與黑板，方便專心調控
            self.target_yaw = 0.0
            self.target_pitch = -0.22
        else:
            norm_x = (mx / max(1, view_w)) * 2.0 - 1.0
            norm_y = (my / max(1, self.height)) * 2.0 - 1.0
            norm_x = max(-1.0, min(1.0, norm_x))
            norm_y = max(-1.0, min(1.0, norm_y))

            # 左右轉頭：-45 度 ~ +45 度 (清楚看到左右兩側其他學生與教室窗戶/門)
            self.target_yaw = norm_x * 0.72
            # 上下俯仰：滑鼠往上 (norm_y=-1) -> pitch=+0.08 (抬頭看黑板奶龍)
            #           滑鼠置中 (norm_y=0)  -> pitch=-0.22 (同時看到前方奶龍與桌上考卷)
            #           滑鼠往下 (norm_y=+1) -> pitch=-0.52 (低頭直視書桌考卷與拉開的抽屜內部小抄)
            self.target_pitch = -norm_y * 0.30 - 0.22

        self.target_yaw = max(-0.85, min(0.85, self.target_yaw))
        self.target_pitch = max(-0.56, min(0.12, self.target_pitch))

        smooth = min(1.0, dt * 10.0)
        self.yaw += (self.target_yaw - self.yaw) * smooth
        self.pitch += (self.target_pitch - self.pitch) * smooth

    def world_to_cam(self, pt):
        """將世界座標 (x, y, z) 轉換為相機空間座標 (cx, cy, cz)"""
        dx = pt[0] - self.pos[0]
        dy = pt[1] - self.pos[1]
        dz = pt[2] - self.pos[2]

        # 1. 繞 Y 軸水平轉頭 (yaw > 0 向右看)
        cos_y = math.cos(self.yaw)
        sin_y = math.sin(self.yaw)
        x1 = dx * cos_y - dz * sin_y
        z1 = dx * sin_y + dz * cos_y
        y1 = dy

        # 2. 繞 X 軸垂直俯仰 (pitch < 0 低頭往下看書桌與抽屜)
        cos_p = math.cos(self.pitch)
        sin_p = math.sin(self.pitch)
        y2 = y1 * cos_p - z1 * sin_p
        z2 = y1 * sin_p + z1 * cos_p
        x2 = x1

        return (x2, y2, z2)

    def project(self, pt):
        """將世界座標投影為 2D 螢幕座標 (sx, sy, cz)"""
        cx, cy, cz = self.world_to_cam(pt)
        if cz < 0.18:
            return None
        center_x = (self.width - 385) * 0.50
        center_y = self.height * 0.48
        sx = center_x + (cx / cz) * self.fov_scale
        sy = center_y - (cy / cz) * self.fov_scale
        return (int(sx), int(sy), cz)

    def clip_and_project_poly(self, pts_3d):
        """對 3D 多邊形進行近平面 (z = 0.20) 裁剪並投影至 2D 螢幕頂點列表"""
        near_z = 0.20
        cam_pts = [self.world_to_cam(p) for p in pts_3d]

        clipped = []
        n = len(cam_pts)
        for i in range(n):
            p1 = cam_pts[i]
            p2 = cam_pts[(i + 1) % n]
            in1 = p1[2] >= near_z
            in2 = p2[2] >= near_z

            if in1 and in2:
                clipped.append(p2)
            elif in1 and not in2:
                t = (near_z - p1[2]) / (p2[2] - p1[2])
                ix = p1[0] + t * (p2[0] - p1[0])
                iy = p1[1] + t * (p2[1] - p1[1])
                clipped.append((ix, iy, near_z))
            elif not in1 and in2:
                t = (near_z - p1[2]) / (p2[2] - p1[2])
                ix = p1[0] + t * (p2[0] - p1[0])
                iy = p1[1] + t * (p2[1] - p1[1])
                clipped.append((ix, iy, near_z))
                clipped.append(p2)

        if len(clipped) < 3:
            return None, 0.0

        center_x = (self.width - 385) * 0.50
        center_y = self.height * 0.48
        screen_pts = []
        avg_z = 0.0
        for cx, cy, cz in clipped:
            sx = int(center_x + (cx / cz) * self.fov_scale)
            sy = int(center_y - (cy / cz) * self.fov_scale)
            screen_pts.append((sx, sy))
            avg_z += cz
        avg_z /= len(clipped)
        return screen_pts, avg_z


class Classroom3DRenderer:
    """負責繪製 3D 教室場景、旁邊其他學生、奶龍監考官、玩家書桌、桌下抽屜與伸手翻小抄動畫"""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.camera = Camera3D(width, height)

        # 教室中旁邊與前排的其他學生座位配置 (中央保留走道讓奶龍巡邏，左右兩側與前排坐滿同學)
        self.classmates = [
            # 玩家左右兩側鄰座同學 (轉頭即可清楚看到)
            {"x": -1.48, "z": 0.48, "coat": (46, 115, 86),  "hair": (28, 24, 22), "type": "write_fast", "name": "左鄰座同學：阿明 (埋頭狂寫)"},
            {"x":  1.48, "z": 0.48, "coat": (70, 82, 118),  "hair": (42, 30, 24), "type": "scratch",    "name": "右鄰座同學：小華 (苦思抓頭)"},
            # 中排走道兩側同學
            {"x": -2.15, "z": 2.35, "coat": (140, 68, 65),  "hair": (25, 22, 20), "type": "look_around","name": "左前外侧同學"},
            {"x": -0.92, "z": 2.45, "coat": (62, 95, 130),  "hair": (35, 28, 22), "type": "write_fast", "name": "左前走道旁同學"},
            {"x":  0.92, "z": 2.45, "coat": (122, 98, 65),  "hair": (30, 25, 20), "type": "nod",        "name": "右前走道旁同學"},
            {"x":  2.15, "z": 2.35, "coat": (85, 110, 90),  "hair": (26, 22, 18), "type": "write_fast", "name": "右前外側同學"},
            # 第一排同學 (靠近講台黑板)
            {"x": -1.35, "z": 4.30, "coat": (55, 90, 100),  "hair": (22, 20, 18), "type": "write_fast", "name": "第一排左同學"},
            {"x":  1.35, "z": 4.30, "coat": (95, 72, 102),  "hair": (38, 28, 22), "type": "scratch",    "name": "第一排右同學"},
        ]

    def draw_poly3d(self, surface, pts_3d, fill_color, border_color=None, border_width=1):
        s_pts, _ = self.camera.clip_and_project_poly(pts_3d)
        if s_pts:
            pygame.draw.polygon(surface, fill_color, s_pts)
            if border_color:
                pygame.draw.polygon(surface, border_color, s_pts, border_width)
        return s_pts

    def render_room_shell(self, surface, teacher):
        """繪製 3D 教室空間：地板、磁磚線、天花板、日光燈、前牆黑板、左牆窗戶、右牆門與佈告欄"""
        surface.fill((195, 205, 215))

        rm_x1, rm_x2 = -3.8, 3.8
        rm_y1, rm_y2 = 0.0, 3.2
        rm_z1, rm_z2 = -1.0, 7.2

        # 1. 教室地板與透視磁磚格線
        floor_pts = [(rm_x1, rm_y1, rm_z1), (rm_x2, rm_y1, rm_z1), (rm_x2, rm_y1, rm_z2), (rm_x1, rm_y1, rm_z2)]
        self.draw_poly3d(surface, floor_pts, (184, 166, 146))

        for gx in [-2.6, -1.3, 0.0, 1.3, 2.6]:
            self.draw_poly3d(surface, [
                (gx - 0.015, 0.005, rm_z1),
                (gx + 0.015, 0.005, rm_z1),
                (gx + 0.015, 0.005, rm_z2),
                (gx - 0.015, 0.005, rm_z2),
            ], (166, 148, 128))

        for gz in [0.5, 1.8, 3.1, 4.4, 5.7]:
            self.draw_poly3d(surface, [
                (rm_x1, 0.005, gz - 0.015),
                (rm_x2, 0.005, gz - 0.015),
                (rm_x2, 0.005, gz + 0.015),
                (rm_x1, 0.005, gz + 0.015),
            ], (166, 148, 128))

        # 2. 天花板與日光燈
        ceil_pts = [(rm_x1, rm_y2, rm_z1), (rm_x1, rm_y2, rm_z2), (rm_x2, rm_y2, rm_z2), (rm_x2, rm_y2, rm_z1)]
        self.draw_poly3d(surface, ceil_pts, (234, 238, 244), (210, 215, 222), 1)
        for lz in [1.4, 3.6, 5.6]:
            for lx in [-1.5, 1.5]:
                self.draw_poly3d(surface, [
                    (lx - 0.55, rm_y2 - 0.02, lz - 0.16),
                    (lx + 0.55, rm_y2 - 0.02, lz - 0.16),
                    (lx + 0.55, rm_y2 - 0.02, lz + 0.16),
                    (lx - 0.55, rm_y2 - 0.02, lz + 0.16),
                ], (253, 255, 255), (200, 215, 230), 1)

        # 3. 左側牆面與教室窗戶
        left_wall = [(rm_x1, rm_y1, rm_z1), (rm_x1, rm_y1, rm_z2), (rm_x1, rm_y2, rm_z2), (rm_x1, rm_y2, rm_z1)]
        self.draw_poly3d(surface, left_wall, (215, 222, 228), (180, 188, 196), 2)
        self.draw_poly3d(surface, [(rm_x1 + 0.01, 0.0, rm_z1), (rm_x1 + 0.01, 0.0, rm_z2), (rm_x1 + 0.01, 0.9, rm_z2), (rm_x1 + 0.01, 0.9, rm_z1)], (185, 195, 205))
        for wz in [0.6, 2.7, 4.8]:
            self.draw_poly3d(surface, [
                (rm_x1 + 0.02, 1.10, wz),
                (rm_x1 + 0.02, 1.10, wz + 1.4),
                (rm_x1 + 0.02, 2.55, wz + 1.4),
                (rm_x1 + 0.02, 2.55, wz),
            ], (165, 218, 250), (110, 85, 65), 3)
            self.draw_poly3d(surface, [
                (rm_x1 + 0.025, 1.10, wz + 0.04),
                (rm_x1 + 0.025, 1.10, wz + 1.36),
                (rm_x1 + 0.025, 1.55, wz + 1.36),
                (rm_x1 + 0.025, 1.55, wz + 0.04),
            ], (115, 185, 125))

        # 4. 右側牆面與教室木門、佈告欄
        right_wall = [(rm_x2, rm_y1, rm_z2), (rm_x2, rm_y1, rm_z1), (rm_x2, rm_y2, rm_z1), (rm_x2, rm_y2, rm_z2)]
        self.draw_poly3d(surface, right_wall, (210, 218, 225), (180, 188, 196), 2)
        self.draw_poly3d(surface, [(rm_x2 - 0.01, 0.0, rm_z1), (rm_x2 - 0.01, 0.0, rm_z2), (rm_x2 - 0.01, 0.9, rm_z2), (rm_x2 - 0.01, 0.9, rm_z1)], (180, 190, 200))
        self.draw_poly3d(surface, [(rm_x2 - 0.02, 0.0, 5.0), (rm_x2 - 0.02, 0.0, 6.2), (rm_x2 - 0.02, 2.25, 6.2), (rm_x2 - 0.02, 2.25, 5.0)], (135, 92, 58), (90, 58, 32), 2)
        self.draw_poly3d(surface, [(rm_x2 - 0.02, 1.05, 1.0), (rm_x2 - 0.02, 1.05, 3.5), (rm_x2 - 0.02, 2.30, 3.5), (rm_x2 - 0.02, 2.30, 1.0)], (65, 105, 85), (130, 95, 60), 3)

        # 5. 前方講台牆面与大黑板
        front_wall = [(rm_x1, rm_y1, rm_z2), (rm_x2, rm_y1, rm_z2), (rm_x2, rm_y2, rm_z2), (rm_x1, rm_y2, rm_z2)]
        self.draw_poly3d(surface, front_wall, (224, 230, 236), (185, 192, 200), 2)

        # 講台木階梯
        self.draw_poly3d(surface, [(-2.4, 0.20, 5.6), (2.4, 0.20, 5.6), (2.4, 0.20, rm_z2), (-2.4, 0.20, rm_z2)], (165, 130, 98), (120, 90, 65), 1)
        self.draw_poly3d(surface, [(-2.4, 0.0, 5.6), (2.4, 0.0, 5.6), (2.4, 0.20, 5.6), (-2.4, 0.20, 5.6)], (140, 105, 75), (110, 80, 55), 1)

        # 黑板木框與黑板面
        bb_frame = [(-2.65, 0.92, rm_z2 - 0.04), (2.65, 0.92, rm_z2 - 0.04), (2.65, 2.55, rm_z2 - 0.04), (-2.65, 2.55, rm_z2 - 0.04)]
        bb_inner = [(-2.52, 1.00, rm_z2 - 0.06), (2.52, 1.00, rm_z2 - 0.06), (2.52, 2.46, rm_z2 - 0.06), (-2.52, 2.46, rm_z2 - 0.06)]
        self.draw_poly3d(surface, bb_frame, (112, 72, 38), (75, 45, 20), 2)
        bb_screen_pts = self.draw_poly3d(surface, bb_inner, (34, 76, 56), (60, 105, 80), 1)

        # 黑板右上方蜂鳴器警示燈
        buzz_pts = [(1.65, 2.12, rm_z2 - 0.08), (2.45, 2.12, rm_z2 - 0.08), (2.45, 2.40, rm_z2 - 0.08), (1.65, 2.40, rm_z2 - 0.08)]
        if teacher.buzzer_active:
            blink = (pygame.time.get_ticks() // 150) % 2 == 0
            b_col = (255, 55, 55) if blink else (255, 210, 0)
        else:
            b_col = (55, 68, 72)
        buzz_screen = self.draw_poly3d(surface, buzz_pts, b_col, (240, 240, 240), 2)

        return bb_screen_pts, buzz_screen

    def _build_desk_and_student_polys(self, cm, ticks):
        x = cm["x"]
        z = cm["z"]
        coat = cm["coat"]
        hair = cm["hair"]
        atype = cm["type"]

        polys = []

        # 學生木書桌
        dx1, dx2 = x - 0.44, x + 0.44
        dz1, dz2 = z + 0.08, z + 0.62
        dy = 0.74
        for lx in [dx1 + 0.05, dx2 - 0.05]:
            polys.append(([(lx - 0.03, 0.0, dz1), (lx + 0.03, 0.0, dz1), (lx + 0.03, dy, dz1), (lx - 0.03, dy, dz1)], (110, 85, 65), None))
        polys.append(([(dx1, 0.55, dz1), (dx2, 0.55, dz1), (dx2, dy, dz1), (dx1, dy, dz1)], (142, 108, 76), (105, 78, 52)))
        polys.append(([(dx1, 0.55, dz2), (dx2, 0.55, dz2), (dx2, dy, dz2), (dx1, dy, dz2)], (152, 118, 84), (105, 78, 52)))
        polys.append(([(dx1, dy, dz1), (dx2, dy, dz1), (dx2, dy, dz2), (dx1, dy, dz2)], (188, 148, 106), (130, 95, 62)))

        # 鄰座桌上的白色考卷
        px1, px2 = x - 0.22, x + 0.22
        pz1, pz2 = z + 0.16, z + 0.50
        polys.append(([(px1, dy + 0.01, pz1), (px2, dy + 0.01, pz1), (px2, dy + 0.01, pz2), (px1, dy + 0.01, pz2)], (248, 248, 242), (200, 200, 195)))

        head_yaw_off = 0.0
        head_y_off = 0.0
        hand_x_off = 0.0
        if atype == "write_fast":
            hand_x_off = math.sin(ticks * 0.016 + x) * 0.06
        elif atype == "scratch":
            head_y_off = math.sin(ticks * 0.006 + x) * 0.02
            hand_x_off = 0.03
        elif atype == "look_around":
            head_yaw_off = math.sin(ticks * 0.003 + z) * 0.07

        # 椅背
        polys.append(([(x - 0.22, 0.35, z - 0.18), (x + 0.22, 0.35, z - 0.18), (x + 0.22, 0.82, z - 0.18), (x - 0.22, 0.82, z - 0.18)], (95, 70, 48), (70, 50, 32)))

        # 學生軀幹
        tx1, tx2 = x - 0.21, x + 0.21
        tz1, tz2 = z - 0.12, z + 0.12
        ty1, ty2 = 0.50, 1.06
        coat_dark = (max(0, coat[0] - 22), max(0, coat[1] - 22), max(0, coat[2] - 22))
        polys.append(([(tx1, ty1, tz1), (tx2, ty1, tz1), (tx2, ty2, tz1), (tx1, ty2, tz1)], coat, coat_dark))
        polys.append(([(tx1, ty1, tz2), (tx2, ty1, tz2), (tx2, ty2, tz2), (tx1, ty2, tz2)], coat, coat_dark))
        polys.append(([(tx1, ty1, tz1), (tx1, ty1, tz2), (tx1, ty2, tz2), (tx1, ty2, tz1)], coat_dark, None))
        polys.append(([(tx2, ty1, tz1), (tx2, ty1, tz2), (tx2, ty2, tz2), (tx2, ty2, tz1)], coat_dark, None))
        polys.append(([(tx1, ty2, tz1), (tx2, ty2, tz1), (tx2, ty2, tz2), (tx1, ty2, tz2)], coat, None))

        # 伸到桌上寫考卷的手臂
        arm_x = x + 0.15 + hand_x_off
        polys.append(([(x + 0.13, 0.76, z + 0.06), (x + 0.23, 0.76, z + 0.06), (arm_x + 0.05, 0.76, z + 0.34), (arm_x - 0.05, 0.76, z + 0.34)], coat, coat_dark))

        return polys, (x + head_yaw_off, 1.21 + head_y_off, z + 0.02), hair, cm["name"]

    def render_classmates_and_teacher(self, surface, teacher, img_nailong, font_small, font_bold):
        ticks = pygame.time.get_ticks()

        sorted_cm = sorted(
            self.classmates,
            key=lambda c: self.camera.world_to_cam((c["x"], 1.0, c["z"]))[2],
            reverse=True
        )

        # 奶龍在 3D 教室中的座標 (z=6.2 在黑板前 -> 巡邏時走到玩家書桌前 z=1.25)
        t_z = 6.20 - teacher.patrol_progress * 4.95
        waddle_x = math.sin(ticks * 0.012) * 0.14 * teacher.patrol_progress if teacher.state == "PATROLLING" else 0.0
        t_x = waddle_x
        t_y = 0.20 * (1.0 - min(1.0, teacher.patrol_progress * 2.5))
        teacher_cam_z = self.camera.world_to_cam((t_x, 1.1, t_z))[2]

        teacher_drawn = False

        podium_polys = [
            ([(-0.72, 0.20, 5.65), (0.72, 0.20, 5.65), (0.72, 1.02, 5.65), (-0.72, 1.02, 5.65)], (125, 82, 48), (85, 55, 30)),
            ([(-0.75, 1.02, 5.60), (0.75, 1.02, 5.60), (0.75, 1.02, 6.02), (-0.75, 1.02, 6.02)], (148, 102, 62), (95, 62, 35)),
        ]
        if t_z >= 5.70:
            self._draw_teacher_3d(surface, teacher, img_nailong, (t_x, t_y, t_z), font_small)
            teacher_drawn = True

        for pts, fc, bc in podium_polys:
            self.draw_poly3d(surface, pts, fc, bc, 2)

        for cm in sorted_cm:
            cm_cam_z = self.camera.world_to_cam((cm["x"], 1.0, cm["z"]))[2]
            if not teacher_drawn and teacher_cam_z >= cm_cam_z:
                self._draw_teacher_3d(surface, teacher, img_nailong, (t_x, t_y, t_z), font_small)
                teacher_drawn = True

            polys, head_pos, hair_col, name_lbl = self._build_desk_and_student_polys(cm, ticks)
            for pts, fc, bc in polys:
                self.draw_poly3d(surface, pts, fc, bc, 1)

            proj_head = self.camera.project(head_pos)
            if proj_head:
                hx, hy, hz = proj_head
                rad = max(6, int(0.145 / hz * self.camera.fov_scale))
                pygame.draw.circle(surface, (238, 195, 165), (hx, hy + int(rad * 0.2)), max(4, int(rad * 0.7)))
                pygame.draw.circle(surface, hair_col, (hx, hy), rad)
                pygame.draw.circle(surface, (238, 195, 165), (hx - rad, hy + 2), max(2, int(rad * 0.26)))
                pygame.draw.circle(surface, (238, 195, 165), (hx + rad, hy + 2), max(2, int(rad * 0.26)))

                if abs(cm["x"]) < 1.7 and cm["z"] < 1.0 and 0 < hx < (self.width - 385):
                    lbl_s = font_small.render(name_lbl, True, (250, 245, 220))
                    bg_r = pygame.Rect(hx - lbl_s.get_width() // 2 - 6, hy - rad - 26, lbl_s.get_width() + 12, 22)
                    pygame.draw.rect(surface, (30, 38, 48), bg_r, border_radius=4)
                    pygame.draw.rect(surface, (120, 175, 220), bg_r, 1, border_radius=4)
                    surface.blit(lbl_s, (bg_r.x + 6, bg_r.y + 2))

        if not teacher_drawn:
            self._draw_teacher_3d(surface, teacher, img_nailong, (t_x, t_y, t_z), font_small)

    def _draw_teacher_3d(self, surface, teacher, img_nailong, pos_3d, font_small):
        tx, ty, tz = pos_3d
        proj_feet = self.camera.project((tx, ty, tz))
        proj_top = self.camera.project((tx, ty + 1.50, tz))
        if not proj_feet or not proj_top:
            return

        fx, fy, _ = proj_feet
        _, top_y, _ = proj_top
        sprite_h = max(35, int(fy - top_y))
        sprite_w = int(sprite_h * 0.82)

        COLOR_NAILONG_YELLOW = (248, 202, 58)
        COLOR_NAILONG_BELLY = (245, 230, 205)
        COLOR_NAILONG_HAND = (85, 75, 65)

        if not teacher.facing_player:
            dragon_rect = pygame.Rect(fx - sprite_w // 2, fy - sprite_h, sprite_w, sprite_h)
            leg_w = max(8, int(sprite_w * 0.26))
            leg_h = max(10, int(sprite_h * 0.25))
            pygame.draw.ellipse(surface, (230, 185, 45), (dragon_rect.x + int(sprite_w * 0.08), dragon_rect.bottom - leg_h + 4, leg_w, leg_h))
            pygame.draw.ellipse(surface, (230, 185, 45), (dragon_rect.right - leg_w - int(sprite_w * 0.08), dragon_rect.bottom - leg_h + 4, leg_w, leg_h))
            pygame.draw.ellipse(surface, COLOR_NAILONG_YELLOW, dragon_rect)
            pygame.draw.ellipse(surface, (255, 220, 95), (dragon_rect.centerx - sprite_w // 4, dragon_rect.y + int(sprite_h * 0.08), sprite_w // 2, int(sprite_h * 0.4)))

            hand_anim = int(math.sin(pygame.time.get_ticks() * 0.012) * max(4, sprite_h * 0.07))
            hx = dragon_rect.right + max(3, int(sprite_w * 0.05))
            hy = dragon_rect.y + int(sprite_h * 0.32) + hand_anim
            pygame.draw.circle(surface, COLOR_NAILONG_HAND, (hx, hy), max(5, int(sprite_w * 0.09)))
            pygame.draw.rect(surface, (255, 255, 255), (hx + 2, hy - 10, 4, 12))

            if teacher.buzzer_active:
                shake = int(math.sin(pygame.time.get_ticks() * 0.04) * max(5, sprite_w * 0.1))
                pygame.draw.ellipse(surface, (255, 80, 80), (dragon_rect.x + shake, dragon_rect.y + int(sprite_h * 0.25), sprite_w, int(sprite_h * 0.55)), 3)
        else:
            if img_nailong:
                aspect = img_nailong.get_width() / img_nailong.get_height()
                tw = max(24, int(sprite_h * aspect))
                scaled = pygame.transform.smoothscale(img_nailong, (tw, sprite_h))
                surface.blit(scaled, (fx - tw // 2, fy - sprite_h))
            else:
                d_rect = pygame.Rect(fx - sprite_w // 2, fy - sprite_h, sprite_w, sprite_h)
                pygame.draw.ellipse(surface, COLOR_NAILONG_YELLOW, d_rect)
                pygame.draw.ellipse(surface, COLOR_NAILONG_BELLY, d_rect.inflate(-int(sprite_w * 0.35), -int(sprite_h * 0.35)))

        lbl = font_small.render("★ 監考官：奶龍教授", True, (255, 240, 170))
        tag_r = pygame.Rect(fx - lbl.get_width() // 2 - 8, top_y - 26, lbl.get_width() + 16, 22)
        pygame.draw.rect(surface, (90, 58, 30), tag_r, border_radius=4)
        pygame.draw.rect(surface, (245, 200, 70), tag_r, 1, border_radius=4)
        surface.blit(lbl, (tag_r.x + 8, tag_r.y + 2))

    def render_player_desk_and_drawer(self, surface, exam, bio, mouse_pos, fonts, anim_helper):
        """
        繪製玩家正前方的 3D 書桌、桌上的考卷、書桌下的立體抽屜、
        以及「小抄在抽屜裡，打開小抄時會伸手拉開抽屜並打開小抄」的完整互動建模！
        """
        font_small, font_main, font_bold = fonts
        lift = bio.emg_signal_level  # 0.0 (抽屜收起) -> 1.0 (伸手拉開抽屜並攤開小抄)

        # ==================== A. 書桌桌面與桌腳建模 (Player's Desk Top) ====================
        desk_x1, desk_x2 = -0.64, 0.64
        desk_y = 0.78
        desk_z_near = 0.36
        desk_z_far = 1.02

        # 書桌左右桌腳與深色抽屜箱體外殼
        self.draw_poly3d(surface, [
            (desk_x1 + 0.02, 0.45, desk_z_near),
            (desk_x2 - 0.02, 0.45, desk_z_near),
            (desk_x2 - 0.02, desk_y, desk_z_near),
            (desk_x1 + 0.02, desk_y, desk_z_near),
        ], (105, 74, 48), (75, 52, 32), 2)

        # 書桌木質主桌面
        self.draw_poly3d(surface, [
            (desk_x1, desk_y, desk_z_near),
            (desk_x2, desk_y, desk_z_near),
            (desk_x2, desk_y, desk_z_far),
            (desk_x1, desk_y, desk_z_far),
        ], (196, 152, 106), (132, 96, 62), 3)

        # 桌面立體前緣木條
        self.draw_poly3d(surface, [
            (desk_x1, desk_y - 0.03, desk_z_near),
            (desk_x2, desk_y - 0.03, desk_z_near),
            (desk_x2, desk_y, desk_z_near),
            (desk_x1, desk_y, desk_z_near),
        ], (152, 110, 72), (105, 74, 48), 2)

        # 書桌右上角的原子筆與橡皮擦
        self.draw_poly3d(surface, [
            (0.45, desk_y + 0.005, 0.46),
            (0.47, desk_y + 0.005, 0.46),
            (0.51, desk_y + 0.005, 0.76),
            (0.49, desk_y + 0.005, 0.76),
        ], (45, 95, 185), (25, 55, 120), 1)
        self.draw_poly3d(surface, [
            (0.48, desk_y + 0.005, 0.39),
            (0.55, desk_y + 0.005, 0.39),
            (0.55, desk_y + 0.005, 0.44),
            (0.48, desk_y + 0.005, 0.44),
        ], (245, 245, 250), (160, 165, 175), 1)

        # ==================== B. 書桌上的考卷 (Exam Paper on Desk) ====================
        paper_3d = [
            (-0.42, desk_y + 0.006, 0.39),
            ( 0.40, desk_y + 0.006, 0.39),
            ( 0.40, desk_y + 0.006, 0.96),
            (-0.42, desk_y + 0.006, 0.96),
        ]
        paper_pts = self.draw_poly3d(surface, paper_3d, (252, 250, 242), (200, 195, 185), 2)

        btn_options = []
        btn_prev = pygame.Rect(0, 0, 0, 0)
        btn_next = pygame.Rect(0, 0, 0, 0)
        btn_submit = pygame.Rect(0, 0, 0, 0)

        if paper_pts and len(paper_pts) >= 4:
            xs = [p[0] for p in paper_pts]
            ys = [p[1] for p in paper_pts]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            pw = max_x - min_x
            ph = max_y - min_y

            if pw > 160 and ph > 80:
                pad_x = int(pw * 0.05)
                content_x = min_x + pad_x
                content_w = pw - pad_x * 2
                curr_y = min_y + 5

                q = exam.current_question()
                head_s = font_small.render(f"【書桌考卷】第 {exam.current_idx + 1} / {len(exam.questions)} 題", True, (41, 128, 185))
                surface.blit(head_s, (content_x, curr_y + 3))

                # 將 < 上一題 / 下一題 > / 提早交卷 置於考卷右上角抬頭列，完全避免與下方抽屜重疊！
                btn_prev = pygame.Rect(content_x + content_w - 280, curr_y, 82, 24)
                btn_next = pygame.Rect(content_x + content_w - 192, curr_y, 82, 24)
                btn_submit = pygame.Rect(content_x + content_w - 104, curr_y, 104, 24)

                for r_btn, lbl, en, b_n in [
                    (btn_prev, "< 上一題", exam.current_idx > 0, "PREV"),
                    (btn_next, "下一題 >", exam.current_idx < len(exam.questions) - 1, "NEXT"),
                ]:
                    d_b, is_p = anim_helper(r_btn, b_n)
                    pygame.draw.rect(surface, (232, 238, 246) if en else (238, 238, 238), d_b, border_radius=4)
                    pygame.draw.rect(surface, (255, 200, 0) if is_p else (180, 185, 195), d_b, 2 if is_p else 1, border_radius=4)
                    ls = font_small.render(lbl, True, (30, 30, 30) if en else (165, 165, 165))
                    surface.blit(ls, (d_b.centerx - ls.get_width() // 2, d_b.centery - ls.get_height() // 2))

                sub_b, sub_p = anim_helper(btn_submit, "SUBMIT")
                pygame.draw.rect(surface, (46, 204, 113), sub_b, border_radius=4)
                pygame.draw.rect(surface, (255, 230, 80) if sub_p else (39, 174, 96), sub_b, 2 if sub_p else 1, border_radius=4)
                ls_sub = font_small.render("★ 提早交卷", True, (255, 255, 255))
                surface.blit(ls_sub, (sub_b.centerx - ls_sub.get_width() // 2, sub_b.centery - ls_sub.get_height() // 2))

                curr_y += 27

                lines = self._wrap_text(q.prompt, font_main, max(200, content_w - 8))
                for ln in lines[:2]:
                    ln_s = font_main.render(ln, True, (25, 25, 25))
                    surface.blit(ln_s, (content_x, curr_y))
                    curr_y += 21

                opt_h = 26
                opt_gap = 4
                for i, opt in enumerate(q.options):
                    raw_r = pygame.Rect(content_x, curr_y + i * (opt_h + opt_gap), content_w, opt_h)
                    btn_options.append(raw_r)
                    b_rect, is_p = anim_helper(raw_r, f"OPT_{i}")

                    is_sel = (q.user_answer == i)
                    is_hov = raw_r.collidepoint(mouse_pos)
                    if is_p:
                        bg_c, bd_c, bw = (205, 230, 255), (255, 200, 0), 3
                    elif is_sel:
                        bg_c, bd_c, bw = (220, 238, 255), (41, 128, 185), 3
                    elif is_hov:
                        bg_c, bd_c, bw = (242, 246, 252), (140, 175, 220), 2
                    else:
                        bg_c, bd_c, bw = (255, 255, 255), (210, 210, 205), 1

                    pygame.draw.rect(surface, bg_c, b_rect, border_radius=4)
                    pygame.draw.rect(surface, bd_c, b_rect, bw, border_radius=4)

                    opt_letter = ["A", "B", "C", "D"][i]
                    c_col = (41, 128, 185) if is_sel else (130, 130, 130)
                    pygame.draw.circle(surface, c_col, (b_rect.x + 16, b_rect.centery), 10, 0 if is_sel else 2)
                    l_s = font_small.render(opt_letter, True, (255, 255, 255) if is_sel else (70, 70, 70))
                    surface.blit(l_s, (b_rect.x + 11, b_rect.centery - l_s.get_height() // 2))

                    o_s = font_small.render(opt[3:], True, (30, 30, 30))
                    surface.blit(o_s, (b_rect.x + 32, b_rect.centery - o_s.get_height() // 2))

        # ==================== C. 書桌下方的立體抽屜建模與伸手翻小抄 (Drawer Under Desk) ====================
        # 當打開小抄 (lift > 0) 時，抽屜從桌下 (z=0.35) 向玩家肚子的方向拉出至 (z=0.14)！
        pull_z = lift * 0.21
        dr_x1, dr_x2 = -0.45, 0.45
        dr_y_bot, dr_y_top = 0.56, 0.72
        dr_z_front = 0.35 - pull_z
        dr_z_back = 0.68 - pull_z

        # 1. 抽屜內部深色木槽底板 (小抄就放在這個抽屜裡！)
        drawer_floor = [
            (dr_x1 + 0.02, dr_y_bot, dr_z_front),
            (dr_x2 - 0.02, dr_y_bot, dr_z_front),
            (dr_x2 - 0.02, dr_y_bot, dr_z_back),
            (dr_x1 + 0.02, dr_y_bot, dr_z_back),
        ]
        df_floor_pts = self.draw_poly3d(surface, drawer_floor, (74, 52, 34), (48, 32, 20), 2)

        # 2. 抽屜左右木側板
        self.draw_poly3d(surface, [(dr_x1, dr_y_bot, dr_z_front), (dr_x1, dr_y_bot, dr_z_back), (dr_x1, dr_y_top, dr_z_back), (dr_x1, dr_y_top, dr_z_front)], (118, 84, 54), (80, 55, 35), 2)
        self.draw_poly3d(surface, [(dr_x2, dr_y_bot, dr_z_front), (dr_x2, dr_y_bot, dr_z_back), (dr_x2, dr_y_top, dr_z_back), (dr_x2, dr_y_top, dr_z_front)], (118, 84, 54), (80, 55, 35), 2)

        # 抽屜左側裡面的課本與鉛筆盒
        self.draw_poly3d(surface, [
            (dr_x1 + 0.04, dr_y_bot + 0.01, dr_z_front + 0.03),
            (dr_x1 + 0.16, dr_y_bot + 0.01, dr_z_front + 0.03),
            (dr_x1 + 0.16, dr_y_bot + 0.01, dr_z_front + 0.22),
            (dr_x1 + 0.04, dr_y_bot + 0.01, dr_z_front + 0.22),
        ], (55, 115, 165), (35, 80, 120), 1)

        # 3. 抽屜前擋板與金屬拉把
        drawer_front = [
            (dr_x1, dr_y_bot - 0.02, dr_z_front),
            (dr_x2, dr_y_bot - 0.02, dr_z_front),
            (dr_x2, dr_y_bot + 0.07, dr_z_front),
            (dr_x1, dr_y_bot + 0.07, dr_z_front),
        ]
        df_pts = self.draw_poly3d(surface, drawer_front, (136, 96, 62), (88, 60, 38), 2)
        self.draw_poly3d(surface, [
            (-0.08, dr_y_bot + 0.015, dr_z_front - 0.005),
            ( 0.08, dr_y_bot + 0.015, dr_z_front - 0.005),
            ( 0.08, dr_y_bot + 0.040, dr_z_front - 0.005),
            (-0.08, dr_y_bot + 0.040, dr_z_front - 0.005),
        ], (218, 188, 105), (140, 115, 55), 1)

        # 4. 抽屜裡的小抄與伸手打開小抄動畫
        if df_pts and len(df_pts) >= 4:
            d_xs = [p[0] for p in df_pts]
            d_ys = [p[1] for p in df_pts]
            cx_mid = (min(d_xs) + max(d_xs)) // 2
            cy_mid = (min(d_ys) + max(d_ys)) // 2

            if lift <= 0.02:
                # 抽屜關閉狀態：在抽屜縫隙露出一點點折疊的黃色小抄紙角
                pygame.draw.polygon(surface, (242, 222, 130), [
                    (cx_mid - 32, cy_mid - 14),
                    (cx_mid + 32, cy_mid - 14),
                    (cx_mid + 38, cy_mid - 4),
                    (cx_mid - 38, cy_mid - 4),
                ])
                pygame.draw.polygon(surface, (180, 145, 55), [
                    (cx_mid - 32, cy_mid - 14),
                    (cx_mid + 32, cy_mid - 14),
                    (cx_mid + 38, cy_mid - 4),
                    (cx_mid - 38, cy_mid - 4),
                ], 1)
                hint_s = font_small.render("【書桌抽屜】小抄藏在抽屜裡 [按空白鍵 / 滑鼠右鍵 / 點EMG 伸手拉開抽屜打開小抄]", True, (255, 240, 175))
                h_rect = pygame.Rect(cx_mid - hint_s.get_width() // 2 - 10, min(self.height - 30, cy_mid + 4), hint_s.get_width() + 20, 24)
                pygame.draw.rect(surface, (42, 30, 20), h_rect, border_radius=5)
                pygame.draw.rect(surface, (215, 175, 85), h_rect, 1, border_radius=5)
                surface.blit(hint_s, (h_rect.x + 10, h_rect.y + 3))
            else:
                # 玩家伸手拉開抽屜並打開抽屜裡的小抄！
                unfold = min(1.0, max(0.20, (lift - 0.08) / 0.92))
                drawer_w = max(280, min(520, int((max(d_xs) - min(d_xs)) * 0.86)))
                box_w = int(drawer_w * (0.65 + 0.35 * unfold))
                box_h = int(115 * unfold + 20)
                box_x = cx_mid - box_w // 2
                box_y = max(self.height - 210, min(self.height - box_h - 14, cy_mid - box_h + 18))

                # 繪製伸進抽屜裡的雙手與前臂 (Reaching Hands into Drawer)
                skin_col = (242, 198, 168)
                skin_dark = (212, 162, 132)
                sleeve_col = (42, 56, 78)

                # 左手：伸出握住抽屜邊緣並扶住小抄左側
                lh_x = box_x + 24
                lh_y = box_y + box_h - 14
                pygame.draw.polygon(surface, sleeve_col, [
                    (lh_x - 52, self.height),
                    (lh_x + 24, self.height),
                    (lh_x + 16, lh_y + 24),
                    (lh_x - 36, lh_y + 24),
                ])
                pygame.draw.ellipse(surface, skin_col, (lh_x - 24, lh_y - 4, 48, 34))
                pygame.draw.ellipse(surface, skin_dark, (lh_x - 14, lh_y - 12, 34, 20))

                # 右手：伸入抽屜內將折疊的小抄往右拉開攤平
                rh_x = box_x + int(box_w * (0.50 + 0.44 * unfold))
                rh_y = box_y + box_h - 14
                pygame.draw.polygon(surface, sleeve_col, [
                    (rh_x - 24, self.height),
                    (rh_x + 52, self.height),
                    (rh_x + 36, rh_y + 24),
                    (rh_x - 16, rh_y + 24),
                ])
                pygame.draw.ellipse(surface, skin_col, (rh_x - 24, rh_y - 4, 48, 34))
                pygame.draw.ellipse(surface, skin_dark, (rh_x - 20, rh_y - 12, 34, 20))

                # 繪製抽屜內展開的小抄紙張
                cheat_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
                paper_alpha = int(min(255, lift * 255))
                pygame.draw.rect(cheat_surf, (254, 249, 192, paper_alpha), (0, 0, box_w, box_h), border_radius=6)
                pygame.draw.rect(cheat_surf, (195, 160, 65, paper_alpha), (0, 0, box_w, box_h), 2, border_radius=6)

                # 小抄紙張中間的十字折痕
                pygame.draw.line(cheat_surf, (220, 195, 120, int(paper_alpha * 0.6)), (box_w // 2, 4), (box_w // 2, box_h - 4), 1)
                pygame.draw.line(cheat_surf, (220, 195, 120, int(paper_alpha * 0.6)), (8, box_h // 2), (box_w - 8, box_h // 2), 1)

                text_alpha, clarity = bio.get_cheat_opacity_and_blur()
                t_head = font_small.render(f"【抽屜內展開小抄】EEG 專注度: {bio.eeg_focus:.0f}% ({clarity})", True, (150, 75, 10))
                t_head.set_alpha(text_alpha)
                cheat_surf.blit(t_head, (12, 6))

                q = exam.current_question()
                hint_lines = self._wrap_text(q.cheat_hint, font_bold, box_w - 24)
                ty = 30
                for line in hint_lines:
                    ls = font_bold.render(line, True, (200, 22, 22))
                    ls.set_alpha(text_alpha)
                    cheat_surf.blit(ls, (12, ty))
                    ty += 25

                if bio.eeg_focus <= 35:
                    w_s = font_small.render("▲ 腦波不專注！抽屜裡的小抄字體幾乎完全透明！", True, (220, 40, 40))
                    w_s.set_alpha(max(90, int(lift * 230)))
                    cheat_surf.blit(w_s, (12, box_h - 24))

                surface.blit(cheat_surf, (box_x, box_y))

                # 繪製壓在小抄正面的左右手大拇指
                pygame.draw.ellipse(surface, skin_col, (lh_x - 8, lh_y - 16, 20, 28))
                pygame.draw.ellipse(surface, skin_col, (rh_x - 12, rh_y - 16, 20, 28))

        return btn_options, btn_prev, btn_next, btn_submit

    def _wrap_text(self, text, font, max_width):
        words = list(text)
        lines = []
        curr = ""
        for char in words:
            test = curr + char
            if font.size(test)[0] <= max_width:
                curr = test
            else:
                lines.append(curr)
                curr = char
        if curr:
            lines.append(curr)
        return lines
