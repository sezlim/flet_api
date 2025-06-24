import flet as ft
import requests
import cv2
import os
import shutil
import threading
import time

API_URL = "http://outapi.mbcnps.com/api/out/programs"
HEADERS = {
    "apikey": "Z6Lh+AskX4amoN+n9ENt9RydkY7FS+dJGNC43r1sJx0="
}

# 전송 대상 폴더 경로 (필요에 따라 수정하세요)
TRANSFER_DESTINATION = r"C:\Users\MBC\Desktop\아웃"  # raw string으로 경로 처리


def get_video_info(file_path):
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return None
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    cap.release()
    return {
        "해상도": f"{width} x {height}",
        "FPS": round(fps, 2),
        "총 프레임 수": total_frames,
        "영상 길이 (초)": round(duration, 2)
    }


def copy_file_with_progress(src_path, dst_path, progress_callback):
    """파일을 복사하면서 진행률을 콜백으로 전달"""
    file_size = os.path.getsize(src_path)
    copied = 0

    with open(src_path, 'rb') as src, open(dst_path, 'wb') as dst:
        while True:
            chunk = src.read(1024 * 1024)  # 1MB씩 복사
            if not chunk:
                break
            dst.write(chunk)
            copied += len(chunk)
            progress = (copied / file_size) * 100
            progress_callback(progress)
            time.sleep(0.01)  # 진행률을 볼 수 있도록 약간의 지연


def main(page: ft.Page):
    page.title = "로그인"
    page.window_width = 500
    page.window_height = 600
    page.bgcolor = "#FFF0F5"  # 연핑크
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER

    def login_attempt(e):
        if username.value == "admin" and password.value == "admin":
            page.clean()
            page.window_width = 1000
            page.window_height = 650
            show_main_ui()
        else:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("로그인 실패: 아이디 또는 비밀번호가 틀립니다.", color="white"),
                bgcolor="red"
            )
            page.snack_bar.open = True
            page.update()

    username = ft.TextField(
        label="아이디",
        autofocus=True,
        label_style=ft.TextStyle(color="black"),
        on_submit=login_attempt
    )

    password = ft.TextField(
        label="비밀번호",
        password=True,
        can_reveal_password=True,
        label_style=ft.TextStyle(color="black"),
        on_submit=login_attempt
    )

    login_view = ft.Column(
        controls=[
            ft.Text("전송 프로그램입니다. (NPS)", size=20, color="#333333"),
            ft.Text("관리자 로그인", size=24, weight="bold", color="#333333"),
            username,
            password,
            ft.ElevatedButton("로그인", on_click=login_attempt)
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=20
    )

    page.add(login_view)

    def show_main_ui():
        page.bgcolor = "#1E1F2F"
        file_picker = ft.FilePicker()
        page.overlay.append(file_picker)

        # 전송 대상 폴더가 없으면 생성
        if not os.path.exists(TRANSFER_DESTINATION):
            try:
                os.makedirs(TRANSFER_DESTINATION)
            except Exception as e:
                print(f"폴더 생성 실패: {e}")

        # 전송 상태 추적 변수
        transfer_active = {"status": False, "thread": None}

        radio_group = ft.RadioGroup(
            value="",
            content=ft.Column(
                scroll=ft.ScrollMode.ALWAYS,
                expand=True,
                spacing=8,
                controls=[
                    ft.Text("프로그램을 조회해주세요.", color="gray", size=12)
                ]
            )
        )
        selected_file_path = {"path": ""}
        selected_file_text = ft.Text("", color="black")
        video_info_text = ft.Column()
        progress_text = ft.Text("", color="black")
        progress_bar = ft.ProgressBar(width=230, visible=False)

        def show_message(msg, bg="blue"):
            page.snack_bar = ft.SnackBar(ft.Text(msg, color="white"), bgcolor=bg)
            page.snack_bar.open = True
            page.update()

        def make_box_with_button(button, content=None):
            return ft.Column(
                [
                    button,
                    ft.Container(
                        width=250,
                        height=260,
                        bgcolor="white",
                        padding=10,
                        border=ft.border.all(1, "#ccc"),
                        border_radius=10,
                        content=content,
                        shadow=ft.BoxShadow(blur_radius=6, color="#00000022", offset=ft.Offset(1, 2)),
                    )
                ],
                spacing=15,
                horizontal_alignment="center"
            )

        # 각 박스의 버튼들을 참조할 수 있도록 생성
        program_button = ft.ElevatedButton(
            text="#1 프로그램 조회",
            icon=ft.Icons.SEARCH,
            bgcolor="#8E05C2",
            color="white",
            icon_color="white",
            width=250,
            height=50,
            on_click=lambda e: on_program_lookup(e)
        )

        file_button = ft.ElevatedButton(
            text="#2 파일 선택",
            icon=ft.Icons.UPLOAD_FILE,
            bgcolor="#00C896",
            color="white",
            icon_color="white",
            width=250,
            height=50,
            on_click=lambda e: on_file_select(e)
        )

        transfer_button = ft.ElevatedButton(
            text="#3 전송하기",
            icon=ft.Icons.SEND,
            bgcolor="#05A8AA",
            color="white",
            icon_color="white",
            width=250,
            height=50,
            on_click=lambda e: on_transfer(e)
        )

        # 리셋 버튼 생성
        reset_button = ft.ElevatedButton(
            "리셋",
            icon=ft.Icons.REFRESH,
            bgcolor="#FF6B6B",
            color="white",
            icon_color="white",
            width=120,
            height=40,
            on_click=lambda e: reset_all(e)
        )

        def enable_all_buttons():
            """모든 버튼 활성화"""
            program_button.disabled = False
            file_button.disabled = False
            transfer_button.disabled = False
            reset_button.disabled = False
            page.update()

        def disable_all_buttons():
            """모든 버튼 비활성화"""
            program_button.disabled = True
            file_button.disabled = True
            transfer_button.disabled = True
            reset_button.disabled = True
            page.update()

        # 박스 컨테이너들 미리 생성
        transfer_box_container = ft.Container(
            width=250,
            height=260,
            bgcolor="white",
            padding=10,
            border=ft.border.all(1, "#ccc"),
            border_radius=10,
            content=ft.Column([progress_text, progress_bar], spacing=10, scroll=ft.ScrollMode.AUTO),
            shadow=ft.BoxShadow(blur_radius=6, color="#00000022", offset=ft.Offset(1, 2)),
        )

        row = ft.Row(
            controls=[
                make_box_with_button(program_button, radio_group),
                make_box_with_button(file_button, ft.Column([selected_file_text, video_info_text], spacing=10)),
                ft.Column([
                    transfer_button,
                    transfer_box_container
                ], spacing=15, horizontal_alignment="center"),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY
        )

        def reset_all(e):
            # 전송 중인 경우 취소
            if transfer_active["status"] and transfer_active["thread"]:
                transfer_active["status"] = False

            print("리셋 버튼 클릭됨")  # 디버깅용

            # 라디오 그룹 초기화
            radio_group.content.controls.clear()
            radio_group.content.controls.append(
                ft.Text("프로그램을 조회해주세요.", color="gray", size=12)
            )
            radio_group.value = ""

            # 파일 선택 초기화
            selected_file_path["path"] = ""
            selected_file_text.value = ""
            video_info_text.controls.clear()

            # 전송 상태 초기화
            progress_text.value = ""
            progress_bar.visible = False
            progress_bar.value = 0

            # 전송 박스 내용 원래대로 복원
            transfer_box_container.content = ft.Column([progress_text, progress_bar], spacing=10,
                                                       scroll=ft.ScrollMode.AUTO)

            # 모든 버튼 활성화
            enable_all_buttons()

            page.update()
            show_message("모든 설정이 초기화되었습니다.", "blue")

        def on_program_lookup(e):
            try:
                resp = requests.get(API_URL, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                result = resp.json()
                programs = result.get("data", [])

                print(f"받아온 프로그램 수: {len(programs)}")  # 디버깅용

                radio_group.content.controls.clear()

                if not programs:
                    # 프로그램이 없을 때 테스트 데이터 추가
                    radio_group.content.controls.append(
                        ft.Text("프로그램이 없습니다.", color="red", size=14)
                    )
                else:
                    for i, prog in enumerate(programs):
                        title = prog.get("title") or f"프로그램 {i + 1}"
                        print(f"프로그램 {i + 1}: {title}")  # 디버깅용

                        radio_group.content.controls.append(
                            ft.Radio(
                                value=title,
                                label=title,
                                fill_color="blue",  # 문자열로 색상 지정
                                label_style=ft.TextStyle(
                                    color="black",
                                    size=12
                                )
                            )
                        )

                # 테스트용 라디오 버튼도 추가
                radio_group.content.controls.append(
                    ft.Radio(
                        value="테스트 프로그램",
                        label="테스트 프로그램 (임시)",
                        fill_color="red",
                        label_style=ft.TextStyle(
                            color="black",
                            size=12,
                            weight="bold"
                        )
                    )
                )

                page.update()
                show_message("프로그램 목록을 가져왔습니다.", "#087f23")

            except Exception as ex:
                print(f"API 오류: {ex}")  # 디버깅용
                # API 실패 시 테스트 데이터 추가
                radio_group.content.controls.clear()
                radio_group.content.controls.extend([
                    ft.Text("API 연결 실패 - 테스트 모드", color="orange", size=12),
                    ft.Radio(
                        value="테스트 프로그램 1",
                        label="테스트 프로그램 1",
                        fill_color="green",
                        label_style=ft.TextStyle(color="black", size=12)
                    ),
                    ft.Radio(
                        value="테스트 프로그램 2",
                        label="테스트 프로그램 2",
                        fill_color="green",
                        label_style=ft.TextStyle(color="black", size=12)
                    )
                ])
                page.update()
                show_message(f"오류 발생: {ex}", "red")

        def on_file_select(e):
            def result_handler(result: ft.FilePickerResultEvent):
                if result.files and result.files[0].path:
                    path = result.files[0].path
                    selected_file_path["path"] = path
                    selected_file_text.value = f"선택된 파일: {os.path.basename(path)}"

                    if not path.lower().endswith((".mp4", ".mov", ".mxf")):
                        video_info_text.controls = [ft.Text("⚠️ 지원되지 않는 형식입니다.", color="red")]
                        page.update()
                        return

                    info = get_video_info(path)
                    if info:
                        video_info_text.controls = [ft.Text(f"{k}: {v}", color="black") for k, v in info.items()]
                    else:
                        video_info_text.controls = [ft.Text("⚠️ 정보를 불러올 수 없습니다.", color="red")]
                    page.update()

            file_picker.on_result = result_handler
            file_picker.pick_files(allow_multiple=False)

        def on_transfer(e):
            print("전송하기 버튼 클릭됨!")  # 디버깅용

            selected = radio_group.value
            path = selected_file_path.get("path", "")

            print(f"선택된 프로그램: {selected}")  # 디버깅용
            print(f"선택된 파일 경로: {path}")  # 디버깅용

            # 1. 프로그램 미선택 시 중단
            if not selected:
                print("프로그램이 선택되지 않음")  # 디버깅용
                progress_text.value = "⚠️ 프로그램을 선택하세요."
                progress_text.color = "red"
                page.update()
                return

            # 2. 파일 미선택 시 중단
            if not path:
                print("파일이 선택되지 않음")  # 디버깅용
                progress_text.value = "⚠️ 파일을 선택하세요."
                progress_text.color = "red"
                page.update()
                return

            # 3. 파일 경로가 유효하지 않으면 중단
            if not os.path.exists(path):
                print(f"파일이 존재하지 않음: {path}")  # 디버깅용
                progress_text.value = "❌ 파일이 존재하지 않습니다."
                progress_text.color = "red"
                page.update()
                return

            # 4. 목적지 파일 경로 설정 및 중복 검사
            filename = os.path.basename(path)
            destination_path = os.path.join(TRANSFER_DESTINATION, filename)

            print(f"목적지 경로: {destination_path}")  # 디버깅용

            if os.path.exists(destination_path):
                print("중복 파일 발견")  # 디버깅용
                progress_text.value = "❌ 똑같은 이름이 있습니다.\n이름 변경 후 전송해주세요."
                progress_text.color = "red"
                page.update()
                return

            # ✅ 여기까지 통과하면 전송 확인 메시지 표시
            print("확인 메시지 표시 시도")  # 디버깅용

            # 확인 메시지 표시
            progress_text.value = f"📁 {filename}\n정말 전송하시겠습니까?"
            progress_text.color = "orange"
            page.update()

            # 확인/취소 버튼을 직접 만들어서 표시
            confirm_button = ft.ElevatedButton(
                "✅ 확인",
                bgcolor="green",
                color="white",
                width=100,
                height=35,
                on_click=lambda e: start_transfer()
            )

            cancel_button = ft.ElevatedButton(
                "❌ 취소",
                bgcolor="red",
                color="white",
                width=100,
                height=35,
                on_click=lambda e: cancel_transfer()
            )

            # 기존 progress_text 아래에 버튼들 추가
            transfer_box_content = ft.Column([
                progress_text,
                progress_bar,
                ft.Row([cancel_button, confirm_button], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
            ], spacing=8)

            # 전송 박스 업데이트
            transfer_box_container.content = transfer_box_content
            page.update()

            def start_transfer():
                print("확인 버튼 클릭됨")  # 디버깅용

                # 버튼들 제거하고 전송 시작
                transfer_box_content.controls.pop()  # 버튼 행 제거

                # 전송 상태 활성화 및 모든 버튼 비활성화
                transfer_active["status"] = True
                disable_all_buttons()

                progress_text.value = "📤 전송 준비 중..."
                progress_text.color = "blue"
                progress_bar.visible = True
                progress_bar.value = 0

                # 전송 취소 버튼 추가
                cancel_transfer_button = ft.ElevatedButton(
                    "❌ 전송 취소",
                    bgcolor="red",
                    color="white",
                    width=150,
                    height=35,
                    on_click=lambda e: cancel_ongoing_transfer()
                )

                transfer_box_content.controls.append(
                    ft.Row([cancel_transfer_button], alignment=ft.MainAxisAlignment.CENTER)
                )
                page.update()

                def update_progress(percent):
                    if transfer_active["status"]:  # 전송이 취소되지 않은 경우에만 업데이트
                        progress_bar.value = percent / 100
                        progress_text.value = f"📤 전송 중... {percent:.1f}%"
                        page.update()

                def actual_transfer():
                    try:
                        print("파일 복사 시작")  # 디버깅용

                        # 취소 가능한 파일 복사
                        file_size = os.path.getsize(path)
                        copied = 0

                        with open(path, 'rb') as src, open(destination_path, 'wb') as dst:
                            while True:
                                if not transfer_active["status"]:  # 전송 취소 확인
                                    print("전송이 취소됨")
                                    # 불완전한 파일 삭제
                                    try:
                                        dst.close()
                                        src.close()
                                        if os.path.exists(destination_path):
                                            os.remove(destination_path)
                                    except:
                                        pass
                                    return

                                chunk = src.read(1024 * 1024)  # 1MB씩 복사
                                if not chunk:
                                    break
                                dst.write(chunk)
                                copied += len(chunk)
                                progress = (copied / file_size) * 100
                                update_progress(progress)
                                time.sleep(0.01)

                        if transfer_active["status"]:  # 전송이 완료된 경우
                            progress_text.value = f"✅ '{filename}' 전송 완료!"
                            progress_text.color = "green"
                            progress_bar.visible = False

                            # 전송 취소 버튼 제거
                            transfer_box_content.controls = [progress_text, progress_bar]

                            # 전송 상태 비활성화 및 모든 버튼 활성화
                            transfer_active["status"] = False
                            enable_all_buttons()

                            page.update()
                            print("파일 복사 완료")  # 디버깅용

                    except Exception as ex:
                        print(f"전송 실패: {ex}")  # 디버깅용
                        progress_text.value = f"❌ 전송 실패: {str(ex)}"
                        progress_text.color = "red"
                        progress_bar.visible = False

                        # 전송 취소 버튼 제거
                        transfer_box_content.controls = [progress_text, progress_bar]

                        # 전송 상태 비활성화 및 모든 버튼 활성화
                        transfer_active["status"] = False
                        enable_all_buttons()

                        page.update()

                # 스레드로 전송 시작
                transfer_thread = threading.Thread(target=actual_transfer)
                transfer_active["thread"] = transfer_thread
                transfer_thread.start()

            def cancel_ongoing_transfer():
                print("전송 취소 버튼 클릭됨")  # 디버깅용
                transfer_active["status"] = False

                progress_text.value = "❌ 전송이 취소되었습니다."
                progress_text.color = "red"
                progress_bar.visible = False

                # 전송 취소 버튼 제거
                transfer_box_content.controls = [progress_text, progress_bar]

                # 모든 버튼 활성화
                enable_all_buttons()

                page.update()

            def cancel_transfer():
                print("취소 버튼 클릭됨")  # 디버깅용

                # 버튼들 제거하고 취소 메시지 표시
                transfer_box_content.controls = [progress_text, progress_bar]
                progress_text.value = "전송이 취소되었습니다."
                progress_text.color = "gray"
                page.update()

        page.add(
            ft.Column(
                [
                    ft.Text("전송 프로그램", size=32, weight="bold", color="white"),
                    ft.Text(f"전송 대상: {TRANSFER_DESTINATION}", size=14, color="white"),
                    ft.Row([
                        reset_button
                    ], alignment=ft.MainAxisAlignment.END),
                    row
                ],
                spacing=20,
                alignment=ft.MainAxisAlignment.START,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )
        )


ft.app(target=main, view=ft.AppView.FLET_APP)