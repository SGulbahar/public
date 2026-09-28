<#
.SYNOPSIS
    SMTP (587 / STARTTLS) üzerinden kullanıcı adı + şifre ile mail gönderir.

.EXAMPLE
    .\Send-Mail587.ps1 -SmtpServer smtp.office365.com -From user@domain.com `
        -To alici@domain.com -Subject "Test" -Body "Merhaba"

.EXAMPLE
    # Şifreyi parametre ile vermek (otomasyon için):
    .\Send-Mail587.ps1 -SmtpServer smtp.office365.com -From user@domain.com `
        -To alici@domain.com -Subject "Test" -Body "Merhaba" `
        -UserName user@domain.com -Password "Sifre123"
#>

param(
    [Parameter(Mandatory)] [string]   $SmtpServer,
    [int]                             $Port = 587,
    [Parameter(Mandatory)] [string]   $From,
    [Parameter(Mandatory)] [string[]] $To,
    [string[]]                        $Cc,
    [Parameter(Mandatory)] [string]   $Subject,
    [string]                          $Body = "",
    [switch]                          $BodyAsHtml,
    [string[]]                        $Attachments,
    [string]                          $UserName,
    [string]                          $Password
)

# Windows PowerShell 5.1 varsayılan olarak TLS 1.0/1.1 kullanabilir; O365 ve çoğu sunucu TLS 1.2 ister
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Kimlik bilgisi: parametre verilmediyse sor
if ([string]::IsNullOrWhiteSpace($UserName)) { $UserName = $From }
if ([string]::IsNullOrWhiteSpace($Password)) {
    $cred = Get-Credential -UserName $UserName -Message "SMTP şifresi"
    $netCred = $cred.GetNetworkCredential()
} else {
    $netCred = New-Object System.Net.NetworkCredential($UserName, $Password)
}

$mail = New-Object System.Net.Mail.MailMessage
$mail.From = $From
foreach ($addr in $To) { $mail.To.Add($addr) }
foreach ($addr in $Cc) { if ($addr) { $mail.CC.Add($addr) } }
$mail.Subject         = $Subject
$mail.Body            = $Body
$mail.IsBodyHtml      = $BodyAsHtml.IsPresent
$mail.SubjectEncoding = [System.Text.Encoding]::UTF8
$mail.BodyEncoding    = [System.Text.Encoding]::UTF8

foreach ($file in $Attachments) {
    if ($file) { $mail.Attachments.Add((New-Object System.Net.Mail.Attachment($file))) }
}

$smtp = New-Object System.Net.Mail.SmtpClient($SmtpServer, $Port)
$smtp.EnableSsl             = $true      # 587'de STARTTLS
$smtp.DeliveryMethod        = [System.Net.Mail.SmtpDeliveryMethod]::Network
$smtp.UseDefaultCredentials = $false     # MUTLAKA Credentials'tan önce
$smtp.Credentials           = $netCred
$smtp.Timeout               = 30000

try {
    $smtp.Send($mail)
    Write-Host "Mail gönderildi -> $($To -join ', ')" -ForegroundColor Green
}
catch {
    Write-Host "Gönderim hatası:" -ForegroundColor Red
    $e = $_.Exception
    while ($e) { Write-Host "  $($e.Message)" -ForegroundColor Red; $e = $e.InnerException }
    exit 1
}
finally {
    $mail.Dispose()
    $smtp.Dispose()
}
