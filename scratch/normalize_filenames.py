import os
import unicodedata

dirs = ["Sol/2014", "Sol/2015", "Sol/2016", "Sol_Excluded/2014", "Sol_Excluded/2015", "Sol_Excluded/2016", "MD_Ref/2014", "MD_Ref/2015", "MD_Ref/2016"]

for d in dirs:
    if not os.path.exists(d): continue
    for f in os.listdir(d):
        nfc_f = unicodedata.normalize('NFC', f)
        if f != nfc_f:
            os.rename(os.path.join(d, f), os.path.join(d, nfc_f))
            print(f"Renamed: {f} -> {nfc_f}")

print("Done normalization.")
