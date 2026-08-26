import { Text, type TextStyle } from "react-native";

/**
 * Renders the light markdown that reaches chat bubbles.
 *
 * Models reply with **bold** and *italics* whether or not anyone asked, and the
 * web portal already renders it, so leaving the asterisks visible here would be
 * the app showing raw text the rest of the product formats. Only bold, italics
 * and inline code are handled - a chat bubble has no use for headings or tables,
 * and a full markdown parser is a dependency this does not need.
 */

const TOKEN = /(\*\*[^*]+\*\*|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`)/g;

export function renderRichText(text: string, style?: TextStyle) {
  if (!text) return null;
  const parts = text.split(TOKEN).filter((part) => part !== "");
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <Text key={index} style={[style, { fontWeight: "700" }]}>
          {part.slice(2, -2)}
        </Text>
      );
    }
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) {
      if (part.length > 2) {
        return (
          <Text key={index} style={[style, { fontStyle: "italic" }]}>
            {part.slice(1, -1)}
          </Text>
        );
      }
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <Text key={index} style={[style, { fontFamily: "Courier" }]}>
          {part.slice(1, -1)}
        </Text>
      );
    }
    return (
      <Text key={index} style={style}>
        {part}
      </Text>
    );
  });
}
