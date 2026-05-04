Build one `.exe` file (launcher version is read from `version.json` at runtime):
`python _build_helper.py build_exe`

Auth server profile switch:
`AINOCRAFT_AUTH_PROFILE=prod|local`

Examples:
PowerShell:
`$env:AINOCRAFT_AUTH_PROFILE="local"; python launcher.py`
`$env:AINOCRAFT_AUTH_PROFILE="prod"; python launcher.py`

cmd.exe:
`set AINOCRAFT_AUTH_PROFILE=local && python launcher.py`
`set AINOCRAFT_AUTH_PROFILE=prod && python launcher.py`

Optional direct override:
`AINOCRAFT_AUTH_BASE_URL=https://your-domain.tld python launcher.py`

Client authlib-injector jar:
- Default path: `<project_root>/injector/authlib-injector-1.2.7.jar`
- Also supported: `<project_root>/authlib-injector-1.2.7.jar`
- Optional override:
  - PowerShell: `$env:AINOCRAFT_AUTHLIB_INJECTOR_JAR="F:\\path\\authlib-injector.jar"; python launcher.py`
  - cmd.exe: `set AINOCRAFT_AUTHLIB_INJECTOR_JAR=F:\path\authlib-injector.jar && python launcher.py`
