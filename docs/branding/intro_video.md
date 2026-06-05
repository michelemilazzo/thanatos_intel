# THANATOS Intro Video — Production Kit

Quello che posso davvero darti come AI agent:
1. **comando ffmpeg pronto** per intro pulita (logo + zoom + fade + sound)
2. **prompt premium** per Runway Gen-3 / Sora / Pika
3. **specs tecniche** per il rendering

Non posso renderizzare video qui — il rendering reale va eseguito sul tuo
host (NAS / ai-mmos-core) o su Runway/Sora.

## 1. Ffmpeg — intro 10s "clean luxury" (esegui sul NAS)

Prerequisiti: `logo.png` (1024×1024, sfondo trasparente).

```bash
ffmpeg -y -loop 1 -i logo.png -t 10 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,
       pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0A0E1A,
       zoompan=z='min(zoom+0.0015,1.25)':d=240:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',
       fade=t=in:st=0:d=1.5,
       fade=t=out:st=8:d=2,
       drawtext=text='THANATOS':fontfile=/usr/share/fonts/truetype/dejavu/DejaVu-Sans-Bold.ttf:fontcolor=0xC8A96E:fontsize=72:x=(w-tw)/2:y=h-180:alpha='if(lt(t,5),0,if(lt(t,7),(t-5)/2,1))',
       drawtext=text='We see what others don\\'t':fontfile=/usr/share/fonts/truetype/dejavu/DejaVu-Sans.ttf:fontcolor=0xC8A96E:fontsize=28:x=(w-tw)/2:y=h-100:alpha='if(lt(t,6),0,if(lt(t,7.5),(t-6)/1.5,1))'" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -preset slow -crf 18 \
  thanatos_intro_clean.mp4
```

Output: `thanatos_intro_clean.mp4` 1920×1080 30fps H.264.

### Aggiungere audio (boom + ambient)

```bash
# 1) scarica un boom CC0 da freesound (es. boom_cinematic_50.wav)
ffmpeg -i thanatos_intro_clean.mp4 -i boom_cinematic_50.wav \
  -filter_complex "[1:a]adelay=4000|4000,volume=0.8[a1]" \
  -map 0:v -map "[a1]" -c:v copy -c:a aac -shortest \
  thanatos_intro_final.mp4
```

## 2. Prompt Runway Gen-3 / Sora — "cinema vero"

Upload: `logo.png`. Settings: 16:9, 10s, High Quality.

```
Ultra cinematic dark intro, black background with deep navy shadows.
Golden particles slowly emerge from darkness, swirling in slow motion,
forming a circular sigil. A hooded angelic figure made of liquid gold
materializes in the center, wings expanding slowly with metallic reflections,
highly detailed feathers.

Volumetric light beams rise from below, creating a divine yet investigative
atmosphere. Camera slowly pushes forward. Particles float like data fragments.

Subtle cyber HUD overlays appear: tracking lines, scanning grids, flickering
coordinates, network graph nodes. Glitch effects increase gradually.

Energy pulse builds inside the figure. At peak intensity, everything
freezes for a split second.

Then: clean sharp reveal of the THANATOS logo (uploaded), perfect gold
reflections on navy background, centered, cinematic lighting.

Text fades in below the logo:
"THANATOS"
"We see what others don't."

Fade to black.

Style: ultra realistic, cinematic lighting, volumetric light, depth of
field, black and gold luxury, dramatic shadows, high contrast, 4K, film
quality, no humans, no faces visible under hood.
```

## 3. Brand specs (DEVONO essere rispettate)

| Token | Hex | Uso |
|---|---|---|
| DARK | `#0A0E1A` | sfondo principale |
| NAVY | `#0D1B3E` | sfondo accent |
| GOLD | `#C8A96E` | testo + logo glow |
| LIGHT | `#F4F4F0` | testo claro |

Font: Helvetica / Eurostile / Orbitron.
Aspect: 16:9 (web hero + youtube) e 1:1 (instagram).
Durata: 8–10s loop, 25–30s versione completa.

## 4. Pipeline raccomandata (production-grade)

```
logo.png
   ↓
[Runway Gen-3 Text-to-Video] → particles_scene.mp4 (5s)
   ↓
[Runway Gen-3 Image-to-Video con logo] → reveal_scene.mp4 (5s)
   ↓
[ffmpeg concat] → thanatos_intro_v1.mp4
   ↓
[DaVinci Resolve / Premiere] → color grade + audio mix
   ↓
thanatos_intro_master.mp4 (1920×1080 + 1080×1080 + 1080×1920)
```

## 5. Versione hero homepage (loop 6s muto)

Stessa pipeline ma:
- niente testo
- niente boom
- loop perfetto (`-stream_loop` + crossfade ultimo→primo frame)
- compressione web: `-crf 24 -preset slower -movflags +faststart`

## Note onestà tecnica

Per il livello "cinema vero" che vuoi servono:
- Runway Gen-3 ($15/mese ~ 125 secondi gen)
- Sora (waitlist)
- o Pika 1.5 ($10/mese)

Il `ffmpeg` qui sopra fa un'intro pulita e professionale ma NON ha:
- ali animate fotorealistiche
- glitch HUD cinematici
- light volumetrico vero

Per quello servono i generatori AI o uno studio VFX. Il tuo budget e
tempo decidono il livello.
