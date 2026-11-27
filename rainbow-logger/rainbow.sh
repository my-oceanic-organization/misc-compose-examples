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

# Maps hue position 0..29 onto the color cube hue wheel used above.
hue_color() {
    seg=$(($1 / 5))
    i=$(($1 % 5))
    case "$seg" in
        0) r=5 g=$i b=0 ;;
        1) r=$((5 - i)) g=5 b=0 ;;
        2) r=0 g=5 b=$i ;;
        3) r=0 g=$((5 - i)) b=5 ;;
        4) r=$i g=0 b=5 ;;
        *) r=5 g=0 b=$((5 - i)) ;;
    esac
    echo $((16 + 36 * r + 6 * g + b))
}

# Numbered lines drawing a rainbow diamond that restarts every 240 lines,
# so any page offset can be checked against the line number and the shape.
print_numbered() {
    total="$1"
    glyphs=".:*#@%"
    n=1
    while [ "$n" -le "$total" ]; do
        k=$(((n - 1) % 240))
        frame=$(((n - 1) / 240 + 1))
        if [ "$k" -lt 120 ]; then w=$((k / 3)); else w=$(((239 - k) / 3)); fi
        g=$(printf '%s' "$glyphs" | cut -c$(((frame - 1) % 6 + 1)))
        body=$(printf "%$((w * 2 + 1))s" "" | tr ' ' "$g")
        color=$(hue_color $((k * 30 / 240)))
        tick=""
        if [ $((n % 10)) -eq 0 ]; then tick=" <- $n"; fi
        printf '%06d frame %03d row %03d/240 |%*s%s[38;5;%sm%s%s[0m%*s|%s\n' \
            "$n" "$frame" "$((k + 1))" $((40 - w)) "" "$E" "$color" "$body" "$E" $((40 - w)) "" "$tick"
        n=$((n + 1))
    done
}

if [ "$1" = "--numbered" ]; then
    print_numbered "${2:-2400}"
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
