[x] correct the `colab\mwtn_notebook.ipynb` to download the end result .zip file to my google drive instead of my laptop because the runtime keeps timing out before the file is done downloading.
✅ For the UX, allow the user to either download the models on their device either via docker "If their devices meet the requirements" or a simplified multi-step guide to set-up the Google Colab path and link with google drive if they will/want Whilast also making sure to point out the **Mobile data costs**
Use screenshots from the `Moises` app and pass it through google stitch so that the UI looks identical.
✅ Also keep in mind that wehn using Colab; the Models aren't downloaded on your dime but using Google's High speed network infrastructure.

✅ Create a smart system for adjusting this; (Extracting notes for bass...
/tmp/ipykernel_1173/953546750.py:21: UserWarning: With fmin=32.703, sr=44100 and frame_length=2048, less than two periods of fmin fit into the frame, which can cause inaccurate pitch detection. Consider increasing to fmin=43.066 or frame_length=2699.
  f0, voiced_flag, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr)
  495 segments found
Extracting notes for vocals...
  734 segments found
Note detection complete.)

# Features to add
    I Audio Separation of Stems: Easily separate vocals, drums, guitar, bass, piano, strings, ukulele and other instruments in any song. Moises is the ultimate vocal remover, voice splitter, and backing track maker app. ✅
 
- Smart Metronome: Instantly generate click tracks that are in sync to the beat of any song. ✅
 
- AI Lyric Transcription: Convert music into text with our AI lyric generator. Supports audio in English, Spanish, Portuguese, French, and Italian. Transcribe lyrics worry free for the best karaoke track maker & editor. ✅
 
- ✅
 
- Audio Speed Changer: Make hard sections easy with 1-click slow down or speed up. Moises BPM detector finds, records & displays the BPM.✅
 
 
- AI Key Detection: Detect and change the song key and instantly transpose chords to all 12 keys. ✅
 
- Collaborative Setlists: Invite collaborators, fine-tune song elements, and centralize all your musical work.
 
- Count in: Set the "count in" period that precedes the playback so you and the band can start on the right beat.✅
 
- Backing Tracks: Make acapella, drums, bass, guitar, karaoke, and piano backing tracks.
 
- Trim and loop music parts: Our AI detects song parts for easy looping. Save time using our free audio editor.
 
- AI Voice Studio: Access high-quality voices from real artists to cover your editing needs.
 
- Export: Extract and share high-quality audio mixes and separated stems, including the metronome click-track. Extract audio stems for use in any track maker or with our voice remover. ✅

Populate the `.github\instructions\AGENTS-instructions.md` ✅

add a feature that estimates the time to completion of load for full run

Also give the options to selectwhether or not the users want to decode the lyrics, what stems to seperate and which not, etc

Start writing tests to see if the software is on track

The settings button is the UI doesen't work (Perhaps API issue)
The logs show 304 errors for 2 APIs (as 
GET /api/user-profile 304 Not Modified (Mozilla/5.0 ...)
GET /api/usage 304 Not Modified (Mozilla/5.0 ...)

And also add the option to pull an already extracted .zip file into the app