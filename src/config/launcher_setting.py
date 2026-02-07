from src.config.system_setting import resource_path


class LauncherSetting:
    name: str = "LoliCraft: Launcher"
    width: int = 1280
    height: int = 720

    @property
    def background(self) -> str:
        return resource_path("src/assets/img/background2.png")

    @property
    def icon(self) -> str:
        return resource_path("src/assets/icon/icon1.png")


launcherSetting = LauncherSetting()
