.\scripts\windows\build-exe.ps1
>>
.\scripts\windows\build-exe.ps1 : File
C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows\build-exe.ps1 cannot be loaded. The
file C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows\build-exe.ps1 is not digitally
signed. You cannot run this script on the current system. For more information about running scripts and setting
execution policy, see about_Execution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170.
At line:1 char:1
+ .\scripts\windows\build-exe.ps1
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
+ CategoryInfo : SecurityError: (:) [], PSSecurityException
+ FullyQualifiedErrorId : UnauthorizedAccess
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os> cd .\scripts\
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts> cd .\windows\
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows> .\build-exe.ps1\
.\build-exe.ps1\ : The term '.\build-exe.ps1\' is not recognized as the name of a cmdlet, function, script file, or
operable program. Check the spelling of the name, or if a path was included, verify that the path is correct and try
again.
At line:1 char:1
+ .\build-exe.ps1\
+ ~~~~~~~~~~~~~~~~
+ CategoryInfo : ObjectNotFound: (.\build-exe.ps1\:String) [], CommandNotFoundException
+ FullyQualifiedErrorId : CommandNotFoundException

PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows> Set-ExecutionPolicy -Scope Process Bypass
>>

Execution Policy Change
The execution policy helps protect you from scripts that you do not trust. Changing the execution policy might expose
you to the security risks described in the about_Execution_Policies help topic at
https:/go.microsoft.com/fwlink/?LinkID=135170. Do you want to change the execution policy?
[Y] Yes [A] Yes to All [N] No [L] No to All [S] Suspend [?] Help (default is "N"): y
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows> .\build-exe.ps1\
.\build-exe.ps1\ : The term '.\build-exe.ps1\' is not recognized as the name of a cmdlet, function, script file, or
operable program. Check the spelling of the name, or if a path was included, verify that the path is correct and try
again.
At line:1 char:1
+ .\build-exe.ps1\
+ ~~~~~~~~~~~~~~~~
+ CategoryInfo : ObjectNotFound: (.\build-exe.ps1\:String) [], CommandNotFoundException
+ FullyQualifiedErrorId : CommandNotFoundException

PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows> .\build-exe\
.\build-exe\ : The term '.\build-exe\' is not recognized as the name of a cmdlet, function, script file, or operable
program. Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
At line:1 char:1
+ .\build-exe\
+ ~~~~~~~~~~~~
+ CategoryInfo : ObjectNotFound: (.\build-exe\:String) [], CommandNotFoundException
+ FullyQualifiedErrorId : CommandNotFoundException

PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows> .\build-exe.ps1
==> Installing BSDK packages (all three) + PyInstaller...
Defaulting to user installation because normal site-packages is not writeable
Obtaining file:///C:/Users/techy/Downloads/BSDK-main/BSDK-main/distributed-ai-os/packages/protocol
Installing build dependencies ... error
error: subprocess-exited-with-error

× installing build dependencies did not run successfully.
│ exit code: 1
╰─> [7 lines of output]
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000002F8BAFAFCB0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=3, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000002F8BAF67ED0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=2, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000002F8BB0C0050>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=1, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000002F8BB0C0190>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=0, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000002F8BB0C02D0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
ERROR: Could not find a version that satisfies the requirement hatchling (from versions: none)
ERROR: No matching distribution found for hatchling
[end of output]

note: This error originates from a subprocess, and is likely not a problem with pip.

[notice] A new release of pip is available: 25.3 -> 26.1.2
[notice] To update, run: python.exe -m pip install --upgrade pip
ERROR: Failed to build 'file:///C:/Users/techy/Downloads/BSDK-main/BSDK-main/distributed-ai-os/packages/protocol' when installing build dependencies
pip install (BSDK packages) failed with exit code 1
At C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows\build-exe.ps1:18 char:32
+ ... EXITCODE -ne 0) { throw "$What failed with exit code $LASTEXITCODE" }
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
+ CategoryInfo : OperationStopped: (pip install (BS...ith exit code 1:String) [], RuntimeException
+ FullyQualifiedErrorId : pip install (BSDK packages) failed with exit code 1

PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os> python.exe -m pip install --upgrade pip
Defaulting to user installation because normal site-packages is not writeable
Requirement already satisfied: pip in c:\python314\lib\site-packages (25.3)
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000002433099F8C0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=3, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x0000024330AB8190>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=2, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x0000024330AB82D0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=1, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x0000024330AB8410>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=0, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x0000024330AB8550>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/

[notice] A new release of pip is available: 25.3 -> 26.1.2
[notice] To update, run: python.exe -m pip install --upgrade pip
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os> python.exe -m pip install --upgrade pip
Defaulting to user installation because normal site-packages is not writeable
Requirement already satisfied: pip in c:\python314\lib\site-packages (25.3)
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001F99197F8C0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=3, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001F991A98190>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=2, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001F991A982D0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=1, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001F991A98410>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/
WARNING: Retrying (Retry(total=0, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001F991A98550>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/pip/

[notice] A new release of pip is available: 25.3 -> 26.1.2
[notice] To update, run: python.exe -m pip install --upgrade pip
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os> .\build-exe.ps1
.\build-exe.ps1 : The term '.\build-exe.ps1' is not recognized as the name of a cmdlet, function, script file, or
operable program. Check the spelling of the name, or if a path was included, verify that the path is correct and try
again.
At line:1 char:1
+ .\build-exe.ps1
+ ~~~~~~~~~~~~~~~
+ CategoryInfo : ObjectNotFound: (.\build-exe.ps1:String) [], CommandNotFoundException
+ FullyQualifiedErrorId : CommandNotFoundException

PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os> cd .\scripts\
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts> cd .\windows\
PS C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows> .\build-exe.ps1
==> Installing BSDK packages (all three) + PyInstaller...
Defaulting to user installation because normal site-packages is not writeable
Obtaining file:///C:/Users/techy/Downloads/BSDK-main/BSDK-main/distributed-ai-os/packages/protocol
Installing build dependencies ... error
error: subprocess-exited-with-error

× installing build dependencies did not run successfully.
│ exit code: 1
╰─> [7 lines of output]
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001919C7DFCB0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=3, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001919C797ED0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=2, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001919C8E0050>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=1, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001919C8E0190>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
WARNING: Retrying (Retry(total=0, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x000001919C8E02D0>: Failed to establish a new connection: [Errno 11001] getaddrinfo failed')': /simple/hatchling/
ERROR: Could not find a version that satisfies the requirement hatchling (from versions: none)
ERROR: No matching distribution found for hatchling
[end of output]

note: This error originates from a subprocess, and is likely not a problem with pip.

[notice] A new release of pip is available: 25.3 -> 26.1.2
[notice] To update, run: python.exe -m pip install --upgrade pip
ERROR: Failed to build 'file:///C:/Users/techy/Downloads/BSDK-main/BSDK-main/distributed-ai-os/packages/protocol' when installing build dependencies
pip install (BSDK packages) failed with exit code 1
At C:\Users\techy\Downloads\BSDK-main\BSDK-main\distributed-ai-os\scripts\windows\build-exe.ps1:18 char:32
+ ... EXITCODE -ne 0) { throw "$What failed with exit code $LASTEXITCODE" }
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
+ CategoryInfo : OperationStopped: (pip install (BS...ith exit code 1:String) [], RuntimeException
+ FullyQualifiedErrorId : pip install (BSDK packages) failed with exit code 1