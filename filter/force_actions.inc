rules {
  AV_UNAVAILABLE {
    action = "soft reject";
    expression = "CLAMAV_UNAVAILABLE";
    message = "Virus scanner temporarily unavailable; please retry";
  }
}
