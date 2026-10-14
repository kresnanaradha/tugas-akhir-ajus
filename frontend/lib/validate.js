// pola tautan rapat, pengecekan yang sama dengan _join() di backend supaya user ditolak seketika. Sengaja longgar (Zoom punya
// banyak subdomain), hanya menangkap yang jelas bukan tautan rapat
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
