clamav {
  type = "clamav";
  symbol = "CLAM_VIRUS";
  symbol_fail = "CLAMAV_UNAVAILABLE";
  servers = "clamav:3310";
  action = "reject";
  scan_mime_parts = true;
  scan_text_mime = true;
  text_part_min_words = 0;
  scan_image_mime = true;
  timeout = 15;
  retransmits = 1;
}
