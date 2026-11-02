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

if [ "$1" = "--once" ]; then
    print_all
    exit 0
fi

interval="${INTERVAL:-2}"
while true; do
    print_all
    sleep "$interval"
done
