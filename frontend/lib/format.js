// Mengubah timestamp ISO (dari data rapat backend) menjadi
// bentuk tampilan {date, time} yang dibutuhkan MeetingRow.
export function formatMeetingDate(isoString) {
  const d = new Date(isoString);
  const now = new Date();
  const startOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);

  let date;
  if (diffDays === 0) date = "Hari ini";
  else if (diffDays === 1) date = "Kemarin";
  else date = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short" }).format(d);

  const time = new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit" }).format(d);
  return { date, time };
}

// Dipakai bersama oleh MeetingRow dan halaman detail rapat.
export const PLATFORM_LABEL = {
  google_meet: "Google Meet",
  zoom: "Zoom",
  upload: "Upload Audio",
};

// sampai 2 inisial dari nama, untuk lingkaran avatar
export function initialsOf(name) {
  return (name || "")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}
