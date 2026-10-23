' Inicia el sistema sin mostrar la ventana negra. Para detenerlo use "Detener Campo Alegre.bat".
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "cmd /c ""Iniciar Campo Alegre.bat"" oculto", 0, False
