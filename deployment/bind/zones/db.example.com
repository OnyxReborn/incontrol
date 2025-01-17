$TTL    86400
@       IN      SOA     ns1.example.com. admin.example.com. (
                        2024011701      ; Serial
                        3600            ; Refresh
                        1800            ; Retry
                        604800          ; Expire
                        86400           ; Minimum TTL
)

; Nameservers
@       IN      NS      ns1.example.com.
@       IN      NS      ns2.example.com.

; A records
@       IN      A       192.0.2.1
www     IN      A       192.0.2.1
mail    IN      A       192.0.2.1
ns1     IN      A       192.0.2.2
ns2     IN      A       192.0.2.3

; AAAA records
@       IN      AAAA    2001:db8::1

; MX records
@       IN      MX      10 mail.example.com.

; CNAME records
ftp     IN      CNAME   www.example.com.

; TXT records
@       IN      TXT     "v=spf1 mx a ip4:192.0.2.0/24 -all"
_dmarc  IN      TXT     "v=DMARC1; p=reject; rua=mailto:dmarc@example.com" 