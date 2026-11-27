#!/bin/sh
# Prints the 16 basic ANSI foreground colors (30-37, 90-97), plain and bold, plus 256-color gradients.

E=$(printf '\033')

print_all() {
    for c in 30 31 32 33 34 35 36 37 90 91 92 93 94 95 96 97; do
        printf '%s[%sm color %s %s[39m %s[1m%s[%sm bold %s %s[0m\n' "$E" "$c" "$c" "$E" "$E" "$E" "$c" "$c" "$E"
    done

    line=""
    for c in 31 33 32 36 34 35 91 93 92 96 94 95; do
        line="$line$E[${c}m####"
    done
    printf '%s%s[0m\n' "$line" "$E"

    print_256_gradient
}

# Walks the hue wheel of the 6x6x6 color cube (index 16 + 36r + 6g + b), then the 24-step grayscale ramp.
print_256_gradient() {
    line=""
    for step in "r g+" "g r-" "g b+" "b g-" "b r+" "r b-"; do
        i=0
        while [ "$i" -lt 5 ]; do
            up=$i
            down=$((5 - i))
            case "$step" in
                "r g+") r=5 g=$up b=0 ;;
                "g r-") r=$down g=5 b=0 ;;
                "g b+") r=0 g=5 b=$up ;;
                "b g-") r=0 g=$down b=5 ;;
                "b r+") r=$up g=0 b=5 ;;
                "r b-") r=5 g=0 b=$down ;;
            esac
            line="$line$E[38;5;$((16 + 36 * r + 6 * g + b))m█"
            i=$((i + 1))
        done
    done
    printf '%s%s[0m\n' "$line" "$E"

    line=""
    n=232
    while [ "$n" -le 255 ]; do
        line="$line$E[38;5;${n}m█"
        n=$((n + 1))
    done
    printf '%s%s[0m\n' "$line" "$E"
}

# Numbered lines drawing a rainbow diamond that restarts every 240 lines,
# so any page offset can be checked against the line number and the shape.
print_numbered() {
    total="$1"
    delay="$2"
    glyphs=".:*#@%"
    last_frame=$(((total - 1) / 240 + 1))
    n=1
    while [ "$n" -le "$total" ]; do
        k=$(((n - 1) % 240))
        frame=$(((n - 1) / 240 + 1))
        if [ "$k" -lt 120 ]; then w=$((k / 3)); else w=$(((239 - k) / 3)); fi
        if [ "$frame" -eq "$last_frame" ]; then
            body=""
            j=0
            while [ "$j" -le $((w * 2)) ]; do
                set -- 31 33 32 36 34 35 91 93 92 96 94 95
                shift $(((j + k) % 12))
                case $((j % 4)) in
                    0) g='*' ;; 1) g='+' ;; 2) g='o' ;; *) g='+' ;;
                esac
                body="$body$E[$1m$g"
                j=$((j + 1))
            done
        else
            g=$(printf '%s' "$glyphs" | cut -c$(((frame - 1) % 6 + 1)))
            body=$(printf "%$((w * 2 + 1))s" "" | tr ' ' "$g")
        fi
        set -- 31 33 32 36 34 35 91 93 92 96 94 95
        shift $((k / 20))
        color=$1
        tick=""
        if [ $((n % 10)) -eq 0 ]; then tick=" <- $n"; fi
        printf '%s[%sm%06d f%03d r%03d |%*s%s[1m%s%s[22;%sm%*s|%s%s[0m\n' \
            "$E" "$color" "$n" "$frame" "$((k + 1))" $((40 - w)) "" "$E" "$body" "$E" "$color" $((40 - w)) "" "$tick" "$E"
        if [ $((n % 10)) -eq 0 ] && [ -n "$delay" ]; then sleep "$delay"; fi
        n=$((n + 1))
    done
}

if [ "$1" = "--numbered" ]; then
    print_numbered "${2:-2400}" "$3"
    exit 0
fi

if [ "$1" = "--once" ]; then
    print_all
    exit 0
fi

interval="${INTERVAL:-2}"
while true; do
    print_all
    sleep "$interval"
done
