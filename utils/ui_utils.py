import os
from kivy.uix.boxlayout import BoxLayout
from kivy.core.image import Image as CoreImage
from kivymd.uix.pickers.datepicker import MDModalInputDatePicker,MDModalDatePicker
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarSupportingText
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image
from kivy.core.window import Window
from datetime import datetime, timedelta
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.metrics import dp
import glob
from kivy.clock import Clock
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.widget import Widget
import shutil, errno, logging
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.utils import get_color_from_hex
from kivy.core.text import LabelBase
from utils.file_utils import ensure_device_mounts,clean_camera_name
from utils.config import LOCAL_PROJECT_ROOT,IST_OFFSET,BG_COLOR,arial_path,resource_path
from utils.logs import logger
import threading
from utils.logic import(
    get_camera_folders,
    on_camera_selected,
    auto_refresh_devices,
    on_device_selected,
    on_date_selected,
    process_images,
    _process_images_thread,
    _process_images_deferred,
    stop_device_monitor,
    eject_device
)
def show_snackbar(message,duration=2):
    MDSnackbar(
        MDSnackbarSupportingText(text=message,theme_font_size="Custom",
    font_size="18sp",   # bigger text too
    halign="center"),
        y=dp(120),
        orientation="horizontal",
        pos_hint={"center_x": 0.5},
        size_hint_x=0.7,
        background_color="teal",
        duration=duration,
    ).open()
class CustomScrollView(ScrollView):
    def _update_scrollbars(self, *largs):
        super()._update_scrollbars(*largs)
        if self._vbar:
            # reduce scrollbar thumb height to 50% of default
            new_height = max(dp(20), self._vbar.size[1] * 0.1)
            self._vbar.size = (self._vbar.size[0], new_height)

class LimitedSpinnerOption(SpinnerOption):
    """Prompt user to enter password and validate it."""
    pass

class CustomLimitedSpinnerOption(LimitedSpinnerOption): 
    """class for customization """ # Inherit your existing one
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0, 0, 0, 0)  # Transparent canvas
        self.color = (0, 0, 0, 1)  # Text color: Black
        self.font_size = '18sp'
        self.height = dp(50)
        self.shorten = True
        self.shorten_from = 'right'  # ✅ Truncates the end
        self.text_size = (dp(180), None)
        self.halign = 'center'  # So the visible part is the start


        with self.canvas.before:
            # Black border (slightly larger rectangle)
            Color(0, 0, 0, 1)  # Black
            self.border_rect = RoundedRectangle(
                pos=(self.x - 1, self.y - 1),
                size=(self.width + 2, self.height + 2)
            )

            # White background rectangle
            Color(1, 1, 1, 1)  # White
            self.bg_rect =Rectangle(
                pos=self.pos,
                size=self.size
            )

        self.bind(pos=self.update_bg, size=self.update_bg)

    def update_bg(self, *args):
        self.border_rect.pos = (self.x - 1, self.y - 1)
        self.border_rect.size = (self.width + 2, self.height + 2)
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
def dropdown_icon(spinner):
    icon_path = resource_path("dropdown_icon.png")

    dropdown_icon = Image(
        source=icon_path,
        size_hint=(None, None),
        size=(16, 16)
    )

    def position_dropdown_icon(instance, value):
        dropdown_icon.pos = (
            instance.x + instance.width - 32,
            instance.y + (instance.height - 16) / 2
        )

    spinner.add_widget(dropdown_icon)
    spinner.bind(pos=position_dropdown_icon, size=position_dropdown_icon)


class SelectionScreen(BoxLayout):
    def __init__(self, screen_manager, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.screen_manager = screen_manager
        self.external_device_path = ""
        self.available_images = []  # tuples (img_path, gmt_ts, ist_ts)
        self.hour_label_map = {}
        self.camera_root = LOCAL_PROJECT_ROOT
        self.start_date = None 
        
        # UI layout similar to your video(2).py
        with self.canvas.before:
            Color(*get_color_from_hex("#Adb3ad"))
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_rect, size=self.update_rect)
        white = (1, 1, 1, 1)

        scroll = ScrollView(size_hint=(1, 1))
        root_layout = BoxLayout(orientation="vertical", spacing=dp(20), padding=[dp(40)] * 4)

        center_anchor = AnchorLayout(size_hint=(1, 1.25))
        grid_layout = GridLayout(
            cols=2, rows=2, spacing=[dp(160), dp(150)], padding=[dp(70)] * 4,
            size_hint=(1, 1.25), size=(dp(950), dp(450)),
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )

        def create_spinner(text):
            spinner = Spinner(
                text=text,
                values=[],
                font_size='24sp',
                background_normal='',            # remove default
                background_color=(0, 0, 0, 0),   # fully transparent
                color=(0, 0, 0, 1),
                size_hint=(None, None),
                size=(dp(300), dp(65)),
                halign='center',
                option_cls=CustomLimitedSpinnerOption,
            )
            spinner.shorten = True
            spinner.shorten_from = 'right'
            spinner.text_size = (dp(270), None)   # limit visible width
            spinner.halign = 'center'

            spinner.dropdown_cls.scroll_type = ['bars', 'content']
            spinner.dropdown_cls.scroll_cls = CustomScrollView
            spinner.dropdown_cls.bar_width = dp(6)

            spinner.dropdown_cls.bar_color = (0.0039, 0.6745, 0.9333, 1) # black scrollbar
  
            spinner.dropdown_cls.bar_inactive_color = (0.7, 0.7, 0.7, 0.6)  # grey when idle

            with spinner.canvas.before:
                Color(1, 1, 1, 1)  # white background
                spinner.bg_rect = RoundedRectangle(
                    pos=spinner.pos,
                    size=spinner.size,
                    radius=[dp(20)]  # corner radius
                )

            # sync background with widget
            def update_bg(instance, value):
                spinner.bg_rect.pos = spinner.pos
                spinner.bg_rect.size = spinner.size

            spinner.bind(pos=update_bg, size=update_bg)
            dropdown_icon(spinner)
            return spinner


        # Camera spinner (user picks camera first)
        self.camera_spinner = create_spinner("Select Camera")
        names, self.camera_map = get_camera_folders(self.camera_root)
        if names is None:  # means root missing or error
            self.show_popup(f"Camera root folder not found: {self.camera_root}")
            names, self.camera_map = ["No Camera"], {}
        self.camera_spinner.values = names


        # self.camera_spinner.bind(text=self.on_camera_selected)
        self.camera_spinner.bind(text=lambda sp, val: on_camera_selected(self, val))
        self.camera_spinner.dropdown_cls.max_height = dp(120)
        dropdown_icon(self.camera_spinner)

        grid_layout.add_widget(self.camera_spinner)

        # Date spinner
        self.start_button = Button(
            text="Select Date",
            font_size='24sp',
            font_name=arial_path,
            size_hint=(None, None),
            size=(dp(300), dp(65)),
            pos_hint={"x": 0.1, "top": 0.9},
            background_color=(0, 0, 0, 0),
            background_normal='',
            color=(0, 0, 0, 1),
            on_press=self.pick_start_date
        )
        with self.start_button.canvas.before:
            Color(*white)
            self.start_button.bg_rect = RoundedRectangle(
                pos=self.start_button.pos,
                size=self.start_button.size,
                radius=[dp(20)]
            )
        self.start_button.bind(pos=lambda instance, val: setattr(self.start_button.bg_rect, 'pos', instance.pos),
                            size=lambda instance, val: setattr(self.start_button.bg_rect, 'size', instance.size))

        # Add calendar icon to SELECT DATE
        calendar_icon = Image(
            source=resource_path("calendar_icon.png"),
            size_hint=(None, None),
            size=(24, 24)
        )
        def position_calendar_icon(instance, value):
            calendar_icon.pos = (
                instance.x + instance.width - 40,
                instance.y + (instance.height - 24) / 2
            )
        self.start_button.add_widget(calendar_icon)
        self.start_button.bind(pos=position_calendar_icon, size=position_calendar_icon)

        # self.add_widget(self.start_button)

       

        grid_layout.add_widget(self.start_button)

        # Hour spinner
        self.hour_spinner = create_spinner("Select Hour")
        self.hour_spinner.dropdown_cls.max_height = dp(120)
        dropdown_icon(self.hour_spinner)
        # 🟢 Prevent user from opening hour spinner without date
        def on_hour_touch(instance, touch):
            if instance.collide_point(*touch.pos):
                if not self.start_date:  # no date picked yet
                    self.show_popup("Please select a date before choosing an hour.", reset_ui=False)
                    return True  # block spinner dropdown
            return False

        self.hour_spinner.bind(on_touch_down=on_hour_touch)

        grid_layout.add_widget(self.hour_spinner)

        # grid_layout.add_widget(self.hour_spinner)

        self.device_spinner = create_spinner("Select Device")
        self.device_spinner.values = ensure_device_mounts()
        # self.device_spinner.bind(text=self.on_device_selected)
        self.device_spinner.bind(text=lambda sp, val: on_device_selected(self, val))
        self.device_spinner.dropdown_cls.max_height = dp(120)
        dropdown_icon(self.device_spinner)
        grid_layout.add_widget(self.device_spinner)

        center_anchor.add_widget(grid_layout)
        bottom_box = AnchorLayout(size_hint=(1, 0.15))

        self.process_button = Button(text="SUBMIT",
                                     font_size='24sp',
                                     size_hint=(None, None),
                                     background_normal='',
                                     background_color=(0, 0, 0, 0),
                                     color=(0, 0, 0, 1), 
                                     size=(dp(270), dp(60)),
                                     on_press=lambda inst: process_images(self))
        with self.process_button.canvas.before:
            Color(*get_color_from_hex("#01acee"))
            self.process_button.bg_rect = RoundedRectangle(pos=self.process_button.pos, size=self.process_button.size, radius=[dp(20)])
        self.process_button.bind(pos=lambda i, v: setattr(self.process_button.bg_rect, 'pos', self.process_button.pos),
                                 size=lambda i, v: setattr(self.process_button.bg_rect, 'size', self.process_button.size))

        bottom_box.add_widget(self.process_button)

        root_layout.add_widget(center_anchor)
        root_layout.add_widget(bottom_box)
        scroll.add_widget(root_layout)
        self.add_widget(scroll)

        Window.bind(on_keyboard=self.on_keyboard)
        # Clock.schedule_interval(lambda dt: self.auto_refresh_devices(), 5)
        Clock.schedule_interval(lambda dt: auto_refresh_devices(self), 0.5)
        logger.info("Selection screen initialized")
    def pick_start_date(self, instance):
        try:
            # 🟢 Block date selection if no camera selected
            if (not self.camera_spinner.text) or self.camera_spinner.text.startswith("Select"):
                self.show_popup("Please select a camera before choosing a date.")
                self.reset_ui_state()
                return

            def show_calendar_picker():
                picker = MDModalDatePicker(
                    year=datetime.now().year,
                    month=datetime.now().month,
                    day=datetime.now().day,
                    mark_today=True,
                )

                def on_ok(instance_date_picker):
                    date = instance_date_picker.get_date()[0]
                    self.start_date = date.strftime('%Y-%m-%d')
                    self.start_button.text = self.start_date
                    instance_date_picker.dismiss()

                    # populate hours
                    on_date_selected(self, self.start_date)

                def on_cancel(instance_date_picker):
                    instance_date_picker.dismiss()

                def on_edit(instance_date_picker):
                    instance_date_picker.dismiss()
                    Clock.schedule_once(lambda dt: show_input_picker(), 0.2)

                picker.bind(on_ok=on_ok, on_cancel=on_cancel, on_edit=on_edit)
                picker.open()

            def show_input_picker():
                input_picker = MDModalInputDatePicker()

                def on_ok_input(instance_date_picker):
                    date = instance_date_picker.get_date()[0]
                    self.start_date = date.strftime('%Y-%m-%d')
                    self.start_button.text = f"Start: {self.start_date}"
                    instance_date_picker.dismiss()

                    # populate hours
                    on_date_selected(self, self.start_date)

                def on_cancel_input(instance_date_picker):
                    instance_date_picker.dismiss()

                def input_edit(instance_date_picker):
                    instance_date_picker.dismiss()
                    Clock.schedule_once(lambda dt: show_calendar_picker(), 0.2)

                input_picker.bind(
                    on_ok=on_ok_input,
                    on_cancel=on_cancel_input,
                    on_edit=input_edit
                )
                input_picker.open()

            # 🟢 Only show calendar if camera was selected
            show_calendar_picker()

        except Exception as e:
            show_snackbar(f"Error opening date picker: {e}")
    
    # def show_success_popup(self, message, mount_point):
    #     """Popup after successful copy with Safe Eject and Close options."""
    #     layout = BoxLayout(orientation="vertical", spacing=20, padding=20)

    #     label = Label(
    #         text=message,
    #         color=(0,0,0,1),
    #         font_size="22sp",
    #         halign="center",
    #         valign="middle"
    #     )
    #     label.bind(size=label.setter("text_size"))

    #     # Buttons layout (centered horizontally)
    #     btn_layout = BoxLayout(
    #         orientation="horizontal",
    #         spacing=20,
    #         size_hint_y=None,
    #         height=60,
    #         size_hint_x=None,
    #         width=dp(350),     # ✅ fixed width to center buttons
    #         pos_hint={"center_x": 0.5}  # ✅ center the whole row
    #     )

    #     # Common button style
    #     def make_btn(text, bg_color):
    #         return Button(
    #             text=text,
    #             size_hint=(None, None),
    #             size=(dp(160), dp(50)),  # ✅ equal size
    #             background_normal='',
    #             background_color=bg_color,
    #             color=(1,1,1,1)
    #         )

    #     eject_btn = make_btn("Safely Eject", (0, 0.6, 0, 1))
    #     close_btn = make_btn("Close", (0.8, 0, 0, 1))

    #     btn_layout.add_widget(eject_btn)
    #     btn_layout.add_widget(close_btn)

    #     layout.add_widget(label)
    #     layout.add_widget(btn_layout)

    #     popup = Popup(
    #         title="",
    #         separator_height=0,
    #         content=layout,
    #         size_hint=(0.6, 0.4),
    #         auto_dismiss=False,
    #         background='',
    #         background_color=(1,1,1,1)
    #     )

    #     def on_eject(*_):
    #         # Disable button immediately
    #         eject_btn.disabled = True
    #         eject_btn.text = "Ejecting..."  # ✅ feedback for user

    #         def run_eject():
    #             success = eject_device(mount_point)
    #             Clock.schedule_once(lambda dt: after_eject(success), 0)

    #         def after_eject(success):
    #             popup.dismiss()
    #             if success:
    #                 self.show_popup("Device safely ejected. You may now remove it.")
    #             else:
    #                 self.show_popup("Please eject the device manually.")
    #             self.reset_ui_state()

    #         # Run eject in background thread (prevents UI freeze)
    #         threading.Thread(target=run_eject, daemon=True).start()

    #     def on_close(*_):
    #         popup.dismiss()
    #         self.reset_ui_state()

    #     eject_btn.bind(on_release=on_eject)
    #     close_btn.bind(on_release=on_close)

    #     popup.open()
    
    def show_success_popup(self, message, mount_point):
        """Popup after successful copy with Safe Eject and Close options."""
        layout = BoxLayout(orientation="vertical", spacing=20, padding=20)

        label = Label(
            text=message,
            color=(0,0,0,1),
            font_size="22sp",
            halign="center",
            valign="middle"
        )
        label.bind(size=label.setter("text_size"))

        btn_layout = BoxLayout(
            orientation="horizontal",
            spacing=20,
            size_hint_y=None,
            height=60,
            size_hint_x=None,
            width=dp(350),
            pos_hint={"center_x": 0.5}
        )

        def make_btn(text, bg_color):
            return Button(
                text=text,
                size_hint=(None, None),
                size=(dp(160), dp(50)),
                background_normal='',
                background_color=bg_color,
                color=(1,1,1,1)
            )

        eject_btn = make_btn("Safely Eject", (0, 0.6, 0, 1))
        close_btn = make_btn("Close", (0.8, 0, 0, 1))

        btn_layout.add_widget(eject_btn)
        btn_layout.add_widget(close_btn)

        layout.add_widget(label)
        layout.add_widget(btn_layout)

        popup = Popup(
            title="",
            separator_height=0,
            content=layout,
            size_hint=(0.6, 0.4),
            auto_dismiss=False,
            background='',
            background_color=(1,1,1,1)
        )

        def on_eject(*_):
            popup.dismiss()

            # Show ejecting popup (blocks UI)
            loading_layout = BoxLayout(orientation="vertical", spacing=15, padding=20)
            loading_label = Label(
                text="Ejecting device...",
                font_size="20sp",
                halign="center",
                valign="middle",
                color=(0,0,0,1)
            )
            loading_label.bind(size=loading_label.setter("text_size"))
            loading_layout.add_widget(loading_label)

            loading_popup = Popup(
                title="",
                separator_height=0,
                content=loading_layout,
                size_hint=(0.4, 0.25),
                auto_dismiss=False,
                background='',
                background_color=(1,1,1,1)
            )
            loading_popup.open()

            def run_eject():
                success = eject_device(mount_point)
                Clock.schedule_once(lambda dt: after_eject(success), 0)

            def after_eject(success):
                loading_popup.dismiss()
                if success:
                    self.show_popup("Device safely ejected. You may now remove it.")
                else:
                    self.show_popup("Please eject the device manually.")
                self.reset_ui_state()

            threading.Thread(target=run_eject, daemon=True).start()

        def on_close(*_):
            popup.dismiss()
            self.reset_ui_state()

        eject_btn.bind(on_release=on_eject)
        close_btn.bind(on_release=on_close)

        popup.open()

    def _show_space_warning_popup(self, required, available, groups, device, camera, date_val, hour_label):
        logger.warning("Low space detected: required=%d MB, available=%d MB",
                       required // (1024*1024), available // (1024*1024))

        msg = (
            f"Not enough space on the device.\n\n"
            f"Required: ~{required // (1024*1024)} MB\n"
            f"Available: ~{available // (1024*1024)} MB\n\n"
            "Please free up space and try again."
        )
        self.show_popup(msg)   # just show popup, no continue/cancel
        self.hide_loading()


    def update_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        # ------------------- Overwrite Confirmation -------------------
    def _show_overwrite_popup(self, message, folder_to_delete, external_device_path, final_folder):
        """Popup asking whether to overwrite existing incidents folder"""
        def show_popup(dt):
            layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
            layout.add_widget(Widget(size_hint_y=1))

            label = Label(
                text=message, font_size='20sp', font_name='Arial',
                size_hint_y=None, height=100, halign='center', valign='middle',
                color=(0, 0, 0, 1)
            )
            label.bind(size=label.setter('text_size'))
            layout.add_widget(label)
            layout.add_widget(Widget(size_hint_y=1))

            btn_layout_outer = BoxLayout(size_hint_y=None, height=40, spacing=10)
            btn_layout_outer.add_widget(Widget())

            btn_layout = BoxLayout(size_hint=(None, None), size=(420, 100), spacing=10)
            yes_btn = Button(text="Yes", size_hint=(None, None), size=(200, 60),
                             background_normal='', background_color=get_color_from_hex("#01acee"), color=(0,0,0,1))
            no_btn = Button(text="No", size_hint=(None, None), size=(200, 60),
                            background_normal='', background_color=get_color_from_hex("#01acee"), color=(0,0,0,1))
            btn_layout.add_widget(yes_btn)
            btn_layout.add_widget(no_btn)
            btn_layout_outer.add_widget(btn_layout)
            btn_layout_outer.add_widget(Widget())
            layout.add_widget(btn_layout_outer)

            popup = Popup(
                title="", separator_height=0, content=layout,
                background='', background_color=(1,1,1,1),
                size_hint=(0.6, 0.4), auto_dismiss=False
            )

            # 🔹 Keep a reference so we can close it on disconnect
            self.active_overwrite_popup = popup

            yes_btn.bind(on_release=lambda x: (
                popup.dismiss(),
                setattr(self, "active_overwrite_popup", None),   # clear reference
                self._on_confirm_overwrite(popup, folder_to_delete, external_device_path, final_folder)
            ))
            no_btn.bind(on_release=lambda x: (
                popup.dismiss(),
                stop_device_monitor(self),
                setattr(self, "active_overwrite_popup", None),   # clear reference
                self.reset_ui_state()
            ))

            popup.open()

        Clock.schedule_once(show_popup)


    def _on_confirm_overwrite(self, popup, folder_to_delete, external_device_path, final_folder):
        """User clicked YES → delete and re-copy"""
        popup.dismiss()
        self.hide_loading() 
        self.show_loading("Deleting existing folder...")
        threading.Thread(target=lambda: self._delete_and_copy(
            folder_to_delete, external_device_path, final_folder
        ), daemon=True).start()

    def _delete_and_copy(self, folder_path, external_device_path, final_folder):
        """Perform safe deletion before copying new incidents"""
        def get_mount_point(path):
            while not os.path.ismount(path):
                new_path = os.path.dirname(path)
                if new_path == path:
                    return None
                path = new_path
            return path

        try:
            # ✅ Check device still mounted
            mount_point = get_mount_point(folder_path)
            if not mount_point or not os.path.ismount(mount_point):
                Clock.schedule_once(lambda dt: self.hide_loading(), 0)
                Clock.schedule_once(lambda dt: self.show_popup("Unable to delete. Device disconnected."), 0)
                return

            if os.path.exists(folder_path):
                shutil.rmtree(folder_path, ignore_errors=True)
                logging.info(f"Deleted old folder: {folder_path}")

        except Exception as e:
            logging.error(f"Failed to delete folder: {e}")
            Clock.schedule_once(lambda dt: self.hide_loading(), 0)
            Clock.schedule_once(lambda dt: self.show_popup(f"Error deleting folder: {e}"), 0)
            return

        # ✅ Continue with normal incident processing
        Clock.schedule_once(lambda dt: self.hide_loading(), 0)

        Clock.schedule_once(lambda dt: self.show_loading("Processing incidents..."), 0)
        threading.Thread(target=lambda: _process_images_deferred(self), daemon=True).start()

    # ------------ UI helpers ------------
    def show_loading(self, message="Processing..."):
        """Show animated spinner with text centered like in video.py"""
        # frame_dir = os.path.join("resources", "spinner_frames")
        frame_dir = resource_path("spinner_frames")
        self.spinner_frames = sorted(glob.glob(os.path.join(frame_dir, "*.png")))
        self.current_frame = 0

        # Spinner image (first frame)
        self.spinner_image = Image(
            source=self.spinner_frames[0],
            size_hint=(None, None),
            size=(64, 64)
        )

        # Center spinner in layout
        spinner_box = AnchorLayout(anchor_x='center', anchor_y='center')
        spinner_box.add_widget(self.spinner_image)

        # Message label
        label = Label(
            text=message,
            font_size='20sp',
            halign='center',
            valign='middle',
            color=(0, 0, 0, 1)
        )
        label.bind(size=label.setter('text_size'))

        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        layout.add_widget(spinner_box)
        layout.add_widget(label)

        self.loading_popup = Popup(
            title='',
            separator_height=0,
            content=layout,
            size_hint=(0.4, 0.3),
            auto_dismiss=False,
            background='',
            background_color=(1, 1, 1, 1)
        )
        self.loading_popup.open()

        # 🔄 Start frame updates
        self.spinner_event = Clock.schedule_interval(self.update_spinner, 0.1)


    def update_spinner(self, dt):
        """Cycle through spinner frames like in video.py"""
        if not hasattr(self, "spinner_frames") or not self.spinner_frames:
            return
        self.current_frame = (self.current_frame + 1) % len(self.spinner_frames)
        self.spinner_image.source = self.spinner_frames[self.current_frame]
        self.spinner_image.reload()

    def hide_loading(self):
        """Stop spinner and close popup"""
        if hasattr(self, "spinner_event") and self.spinner_event:
            self.spinner_event.cancel()
            self.spinner_event = None
        if hasattr(self, "loading_popup") and self.loading_popup:
            self.loading_popup.dismiss()
            self.loading_popup = None

    def reset_ui_state(self):
        """Reset UI elements to initial state after any popup or completion."""
        self.camera_spinner.text = "Select Camera"
        # self.camera_spinner.values = self.get_camera_folders()
        # self.camera_spinner.values = get_camera_folders(self.camera_root)
        names, self.camera_map = get_camera_folders(self.camera_root)
        self.camera_spinner.values = names

        self.start_date = None
        self.start_button.text = "Select Date"   # ✅ reset the button label

        self.hour_spinner.text = "Select Hour"
        self.hour_spinner.values = []

        self.device_spinner.text = "Select Device"
        self.device_spinner.values = ensure_device_mounts()

        self.available_images.clear()
        self.hour_label_map.clear()
        logger.info("UI reset to initial state")


    def show_popup(self, message,reset_ui=True):
        """Show a clean popup with only message and close button (no title bar or horizontal line)."""

        # Message label
        message_label = Label(
            text=message,
            color=(0,0,0,1),
            font_size='24sp',
            font_name=arial_path,
            halign='center',
            valign='middle',
            size_hint=(None, None),
            text_size=(dp(400), None)
        )
        message_label.bind(texture_size=lambda instance, value: setattr(instance, 'size', value))

        # Close button
        close_button = Button(
            text='X',
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            background_normal="",
            background_color=(1, 0,0,0.8),
            color=(1,1,1, 1),
            bold=True,
            pos_hint={"right": 1, "top": 1}
        )

        # Layout
        layout = BoxLayout(
            orientation='vertical',
            padding=dp(20),
            spacing=dp(10),
            size_hint=(None, None)
        )
        layout.add_widget(close_button)
        layout.add_widget(message_label)

        def open_popup(*_):
            popup_width = message_label.width + dp(60)
            popup_height = message_label.height + dp(100)
            layout.size = (popup_width, popup_height)

            popup = Popup(
                title='',  # ✅ Leave as empty string
                separator_height=0,  # ✅ This removes the horizontal line!
                content=layout,
                size_hint=(None, None),
                size=(popup_width, popup_height),
                background='',
                background_color=(1, 1, 1, 1),
                auto_dismiss=False
            )

            def on_close(*_):
                popup.dismiss()
                if reset_ui:
                    self.reset_ui_state()

            close_button.bind(on_release=on_close)

            popup.open()

        Clock.schedule_once(open_popup, 0)

    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        if key == 27:  # disable escape default exit
            return True
        return False


class IncidentScreen(BoxLayout):
    # Keep a lightweight incidents screen in-case you want to show grouped previews.
    def __init__(self, screen_manager, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.screen_manager = screen_manager
        with self.canvas.before:
            Color(*get_color_from_hex("#Adb3ad"))
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size