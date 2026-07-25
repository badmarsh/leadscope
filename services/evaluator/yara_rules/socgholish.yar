rule SocGholish_FakeUpdate {
    meta:
        description = "SocGholish fake browser update lure and C2 loader"
        malware_family = "socgholish"
        sneakiness_tier = "A"
    strings:
        $b64_loader = /eval\(atob\([\"'][A-Za-z0-9+\/]{30,}[\"']\)\)/
        $update_lure1 = "UpdateRequired" nocase
        $update_lure2 = "BrowserUpdate" nocase
        $c2_pattern = /[a-z0-9]{8,15}\.js\?ver=[0-9]{4,}/
    condition:
        $b64_loader or (any of ($update_lure*) and $c2_pattern)
}
