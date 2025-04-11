# Define la carpeta raíz de tu proyecto
$proyectoRaiz = "C:\Users\GGTECH\Documents\PERSONAL\ARKHAM"

# Nombre del archivo de salida (se recomienda ubicarlo fuera del contenido exportado o controlarlo)
$archivoSalida = "contenido_proyecto.txt"

# Función para procesar archivos en una carpeta de forma recursiva
function ProcesarCarpeta {
    param(
        [string]$carpeta
    )

    # Obtiene todos los archivos DIRECTAMENTE en la carpeta
    $archivos = Get-ChildItem -Path $carpeta -File

    foreach ($archivo in $archivos) {
        # Omitir el archivo de salida para evitar incluirlo en la exportación
        if ($archivo.Name -eq $archivoSalida) { continue }
        
        # Ignorar archivos con las extensiones especificadas
        if ($archivo.Extension -in ".woff", ".woff2", ".jpg", ".png", ".webp") { continue }

        # Agrega la ruta del archivo al archivo de salida
        "Archivo: $($archivo.FullName)" | Out-File -FilePath $archivoSalida -Append -Encoding UTF8
        "--------------------------------------------------" | Out-File -FilePath $archivoSalida -Append -Encoding UTF8

        # Intenta leer y escribir el contenido del archivo
        try {
            Get-Content $archivo.FullName -ErrorAction SilentlyContinue | Out-File -FilePath $archivoSalida -Append -Encoding UTF8
        } catch {
            Write-Warning "Error al leer el archivo: $($archivo.FullName) - $($_.Exception.Message)"
            "Error al leer el archivo: $($archivo.FullName) - $($_.Exception.Message)" | Out-File -FilePath $archivoSalida -Append -Encoding UTF8
        }

        # Agrega líneas en blanco para separar archivos
        "" | Out-File -FilePath $archivoSalida -Append -Encoding UTF8
        "" | Out-File -FilePath $archivoSalida -Append -Encoding UTF8
    }

    # Obtiene todas las subcarpetas DIRECTAMENTE en la carpeta
    $subcarpetas = Get-ChildItem -Path $carpeta -Directory

    foreach ($subcarpeta in $subcarpetas) {
        # Llama recursivamente a la función para procesar la subcarpeta
        ProcesarCarpeta -carpeta $subcarpeta.FullName
    }
}

# Inicia el procesamiento desde la carpeta raíz del proyecto
ProcesarCarpeta -carpeta $proyectoRaiz