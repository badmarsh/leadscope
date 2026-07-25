rule Balada_Injector {
    meta:
        description = "Balada Injector fake plugin and redirect stub"
        malware_family = "balada"
        sneakiness_tier = "B"
    strings:
        $iframe_inject = /<iframe[^>]+src=[\"'][^\"']{0,10}(trck|stat|cdn)\.[^\"']+[\"']/ nocase
        $obf_eval = /String\.fromCharCode\(\s*\d+(\s*,\s*\d+){15,}\s*\)/
        $balada_loader = /eval\(function\(p,a,c,k,e,d\)/
    condition:
        any of them
}
