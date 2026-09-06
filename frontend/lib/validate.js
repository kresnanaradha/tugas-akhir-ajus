// Meeting link patterns — matches the check on the backend (app.py's
// _join()) so the user gets the same rejection instantly instead of after
// a round trip. Deliberately permissive (Zoom has many subdomains like
// us02web.zoom.us, personal meeting room URLs, etc.) — the goal is catching
// "this obviously isn't a meeting link at all", not perfectly validating one.
const PATTERNS = {
  google_meet: /^https?:\/\/meet\.google\.com\/[a-z0-9-]+/i,
  zoom: /^https?:\/\/([a-z0-9-]+\.)?zoom\.us\/(j|wc\/join)\/\d+/i,
};

export function isValidMeetingUrl(platform, url) {
  const pattern = PATTERNS[platform];
  return pattern ? pattern.test(url.trim()) : true;
}

export const MEETING_URL_HINTS = {
  google_meet: "Harus link Google Meet, mis. https://meet.google.com/xxx-xxxx-xxx",
  zoom: "Harus link Zoom, mis. https://zoom.us/j/1234567890",
};
