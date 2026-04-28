/**
 * Custom marked tokenizer extension that fixes URL boundary detection for
 * non-ASCII characters (CJK, Cyrillic, Arabic, fullwidth punctuation, etc.).
 *
 * The default GFM autolink regex uses `[^\s<]*` which greedily matches any
 * non-whitespace after a URL, causing text like "https://example.com/path中文"
 * to treat "中文" as part of the URL.
 */

const NON_URL_CHAR_REGEX =
	/[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u3400-\u4dbf\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff]/;

const GFM_URL_REGEX = /^((?:ftp|https?):\/\/|www\.)(?:[a-zA-Z0-9\-]+\.?)+[^\s<]*/;

const BACKPEDAL_REGEX =
	/(?:[^?!.,:;*_'"~()&]+|\([^)]*\)|&(?![a-zA-Z0-9]+;$)|[?!.,:;*_'"~)]+(?!$))+/;

export default function () {
	return {
		tokenizer: {
			url(src: string) {
				const cap = GFM_URL_REGEX.exec(src);
				if (!cap) return false;

				let text = cap[0];

				const nonAsciiBreak = text.search(NON_URL_CHAR_REGEX);
				if (nonAsciiBreak !== -1) {
					text = text.substring(0, nonAsciiBreak);
				}

				let prevText;
				do {
					prevText = text;
					const m = BACKPEDAL_REGEX.exec(text);
					text = m ? m[0] : text;
				} while (prevText !== text);

				if (!text) return false;

				const href = cap[1] === 'www.' ? 'http://' + text : text;
				return {
					type: 'link' as const,
					raw: text,
					text,
					href,
					tokens: [{ type: 'text' as const, raw: text, text }]
				};
			}
		}
	};
}
