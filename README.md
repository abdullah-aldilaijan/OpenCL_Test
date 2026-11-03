# OpenCL ZIP prototype

Run Setup.cmd once to install standalone Python and dependencies without Anaconda. Then run Run.cmd. Open a new terminal after setup to use the global python command.

## Use

The single dropdown lists the detected CPU and usable OpenCL GPUs. Select a processor, then Compress file or Compress folder. Both CPU and GPU choices now create standard .zip archives. Save folder archives outside the source folder. Restore archive extracts a ZIP to a new destination folder. Earlier .oclr and .folder.oclr archives can still be restored.

CPU compression uses Python's DEFLATE implementation. GPU compression uses the new OpenCL encoder in gpu_zip.py and deflate.cl. Match search and fixed-Huffman DEFLATE bit encoding run on the selected GPU; Python handles I/O, CRC-32, and ZIP/ZIP64 headers. GPU compression processes independent 32 KiB chunks in batches of up to 256. Unhelpful chunks use standard uncompressed DEFLATE blocks. No CPU compressor is used in the GPU ZIP creation path. This is a new prototype, not an implementation of 7-Zip or Zstandard. It does not guarantee smaller output or a speed advantage.

Standard ZIP extraction inside the app currently runs on the CPU. Windows and ordinary ZIP readers can also extract these files without this application. GPU DEFLATE decoding has not been implemented for ZIP. Earlier GPU archive formats keep their existing GPU/CPU decoding support.

## Verification

Both RTX 5060 and Intel Iris Xe were tested against Python's independent zlib/ZIP decoders with random data, repeated data, all byte values, empty files, Unicode names, and nested/empty directories. A multiple-batch archive with more than 9 MB of source bytes also passed Windows Expand-Archive and SHA-256 comparison of extracted files. Deflate block boundaries, match lengths/distances, and raw fallback blocks were tested. ZIP64 headers are emitted and tested on small archives; files larger than 4 GiB have not yet been exercised in this version. CPU ZIP creation and legacy readers remain available.

## Limits

Folders preserve names, directory structure and file bytes, not all Windows permissions or alternate data streams. Links and junctions are rejected. Source folders must remain unchanged during archiving. Existing outputs are refused; output archives are staged before publishing. Temporary disk space is needed for the staged ZIP. Very large collections need memory for their central-directory entries, but file data is streamed in bounded batches. Already-compressed content may shrink little or grow slightly. This release has not been benchmarked against the user's full 14.4 GB folder.

See SETUP.md for installation details. The installer requires WinGet and internet access; working GPU OpenCL drivers must already be installed. The application environment is this folder's .venv and is independent of Anaconda.

Format references: https://www.rfc-editor.org/rfc/rfc1951 and https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
