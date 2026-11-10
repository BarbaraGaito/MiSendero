import { StyleProp, StyleSheet, Text, TextStyle, View, ViewStyle } from "react-native";
import Svg, { G, Path } from "react-native-svg";

type LogoTone = "light" | "dark";
type LogoLayout = "stacked" | "horizontal";

type MiSenderoLogoProps = {
  layout?: LogoLayout;
  markSize?: number;
  showWordmark?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
  tone?: LogoTone;
  wordmarkSize?: number;
};

const brandColors = {
  lightGreen: "#D8F0BD",
  neutral: "#DFDFDF",
  darkGreen: "#0F4331",
  leafGreen: "#53906F",
};

const leafPath =
  "M8040 8219 c-993 -181 -1770 -329 -1970 -375 -448 -104 -732 -259 -1015 -556 -208 -217 -357 -478 -431 -753 -42 -157 -70 -361 -150 -1095 -71 -656 -76 -721 -65 -785 31 -189 178 -356 360 -409 90 -26 193 -20 476 29 143 25 456 80 695 121 464 80 578 104 733 154 521 167 958 604 1147 1144 63 183 92 373 230 1521 22 187 59 490 81 673 37 309 39 354 21 351 -4 0 -54 -10 -112 -20z m-634 -846 c-4 -38 -43 -319 -87 -626 -84 -589 -111 -723 -176 -875 -84 -196 -261 -410 -436 -526 -176 -117 -266 -145 -927 -290 -658 -144 -701 -153 -706 -145 -2 4 11 124 31 266 20 142 51 368 70 503 19 135 39 283 45 330 45 356 144 582 344 789 140 144 301 249 486 316 77 28 348 94 885 216 171 39 342 79 380 89 104 27 99 30 91 -47z";

const ringPath =
  "M5975 9985 c-502 -49 -921 -167 -1343 -379 -795 -398 -1394 -1042 -1750 -1881 -180 -423 -276 -874 -289 -1350 -9 -345 21 -631 103 -965 191 -780 647 -1500 1265 -1996 147 -118 367 -266 483 -324 88 -45 89 -45 195 -45 95 0 112 3 166 28 76 35 138 95 178 172 30 56 32 66 32 165 0 94 -3 111 -28 165 -36 76 -93 136 -182 187 -355 207 -712 543 -942 886 -224 335 -366 671 -446 1058 -45 214 -52 294 -52 584 1 294 10 384 62 620 95 430 291 846 566 1199 106 136 324 356 457 461 441 350 957 563 1511 625 173 19 488 19 654 0 673 -78 1282 -375 1750 -856 229 -235 383 -453 530 -754 161 -328 260 -669 295 -1014 13 -133 13 -439 0 -572 -67 -671 -369 -1307 -849 -1787 -168 -168 -344 -305 -568 -441 -144 -88 -195 -149 -223 -270 -40 -168 42 -346 195 -424 49 -25 75 -31 146 -35 113 -6 169 11 306 92 251 149 466 317 693 545 574 575 946 1327 1056 2131 21 157 30 598 15 775 -72 862 -444 1680 -1051 2309 -269 278 -625 538 -986 719 -374 188 -828 320 -1264 367 -160 18 -530 21 -685 5z";

const compassPath =
  "M6885 6921 c-16 -10 -138 -80 -270 -156 -457 -262 -750 -439 -788 -474 -64 -60 -88 -110 -187 -381 -21 -58 -79 -217 -129 -353 -50 -137 -91 -250 -91 -253 0 -11 34 2 193 74 95 43 282 128 416 188 319 142 331 152 438 373 141 292 463 981 463 991 0 14 -10 11 -45 -9z m-707 -710 c80 -41 122 -111 122 -201 0 -71 -23 -124 -72 -165 -53 -45 -95 -58 -166 -52 -116 9 -193 87 -200 201 -6 97 36 173 121 215 55 27 144 28 195 2z";

export function MiSenderoLogo({
  layout = "stacked",
  markSize = 96,
  showWordmark = true,
  style,
  textStyle,
  tone = "light",
  wordmarkSize = 42,
}: MiSenderoLogoProps) {
  const isLight = tone === "light";
  const primaryFill = isLight ? brandColors.lightGreen : brandColors.leafGreen;
  const secondaryFill = isLight ? brandColors.neutral : brandColors.darkGreen;
  const wordmarkColor = isLight ? brandColors.lightGreen : brandColors.darkGreen;

  return (
    <View accessible accessibilityRole="image" accessibilityLabel="Logo de MiSendero" testID="misendero-logo"
      style={[styles.container, layout === "horizontal" ? styles.row : styles.column, style]}>
      <Svg width={markSize} height={markSize} viewBox="0 0 1254 1254">
        <G transform="translate(0 1254) scale(0.1 -0.1)" fill={secondaryFill}>
          <Path d={leafPath} />
        </G>
        <G transform="translate(0 1254) scale(0.1 -0.1)" fill={primaryFill}>
          <Path d={ringPath} />
          <Path d={compassPath} />
        </G>
      </Svg>
      {showWordmark ? (
        <Text
          style={[
            styles.wordmark,
            {
              color: wordmarkColor,
              fontSize: wordmarkSize,
              lineHeight: Math.round(wordmarkSize * 1.08),
            },
            textStyle,
          ]}
        >
          MiSendero
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    justifyContent: "center",
  },
  column: {
    gap: 10,
  },
  row: {
    flexDirection: "row",
    gap: 12,
  },
  wordmark: {
    fontFamily: "BricolageGrotesque_800ExtraBold",
    fontWeight: "800",
    letterSpacing: 0,
  },
});
