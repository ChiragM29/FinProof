# extension

Chrome extension (Manifest V3). On a YouTube video it reads the video id, asks the FinProof backend for the card and shows it under the video title.

## Load it

1. Start the backend (see the main README).
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick this folder.
3. Open any YouTube video. The card appears under the title.

The toolbar popup turns the card on or off and sets the backend address (default `http://localhost:8000`).

## Safety

- No API keys in the extension. It only talks to the FinProof backend.
- Permissions: `storage` for the two settings, and the backend address. It runs on YouTube pages only.
- The card is built with `textContent` inside a shadow root, so text from videos can't inject code.
