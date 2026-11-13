// Run the real player and emubase against a deterministic SDL audio sink.
// No window, audio hardware, game disk, or wall-clock waits are needed.
#define main PlayerMain
#include "uknc-play.cpp"
#undef main

#include <algorithm>

static uint32_t clockMs, frames, queuedSamples, fraction, underruns;
static uint32_t totalSamples, starts, maxQueued, firstStartSamples;
static bool paused = true, stall = false;
static int failures = 0;

static void Check(const char *name, bool ok)
{
    printf("[%s] %s\n", ok ? "ok" : "FAIL", name);
    if (!ok) failures++;
}

static void Advance(uint32_t ms)
{
    clockMs += ms;
    if (paused) return;
    fraction += ms * SAMPLERATE;
    uint32_t consumed = fraction / 1000;
    fraction %= 1000;
    if (consumed > queuedSamples) underruns++;
    queuedSamples -= std::min(consumed, queuedSamples);
}

extern "C" {
int SDL_Init(uint32_t) { return 0; }
void SDL_Quit() {}
const char *SDL_GetError() { return "test sink"; }
SDL_Window *SDL_CreateWindow(const char *, int, int, int, int, uint32_t)
{ return reinterpret_cast<SDL_Window *>(1); }
SDL_Renderer *SDL_CreateRenderer(SDL_Window *, int, uint32_t)
{ return reinterpret_cast<SDL_Renderer *>(1); }
int SDL_RenderSetLogicalSize(SDL_Renderer *, int, int) { return 0; }
SDL_Texture *SDL_CreateTexture(SDL_Renderer *, uint32_t, int, int, int)
{ return reinterpret_cast<SDL_Texture *>(1); }
int SDL_UpdateTexture(SDL_Texture *, const void *, const void *, int) { return 0; }
int SDL_RenderClear(SDL_Renderer *) { return 0; }
int SDL_RenderCopy(SDL_Renderer *, SDL_Texture *, const void *, const void *) { return 0; }
void SDL_RenderPresent(SDL_Renderer *)
{
    ++frames;
    // Render jitter within a frame budget, plus one deliberate host stall.
    Advance(stall && frames == 100 ? 200 : 1 + frames % 13);
}
int SDL_PollEvent(SDL_Event *event)
{
    if (frames == 249)
    {
        event->type = SDL_QUIT_EVENT;
        ++frames;
        return 1;
    }
    return 0;
}
uint32_t SDL_GetTicks() { return clockMs; }
void SDL_Delay(uint32_t ms) { Advance(ms); }
int SDL_InitSubSystem(uint32_t) { return 0; }
uint32_t SDL_OpenAudioDevice(const char *, int, const SDL_AudioSpec *want,
                             SDL_AudioSpec *, int)
{
    Check("device format matches core", want->freq == SAMPLERATE &&
          want->format == AUDIO_S16LSB && want->channels == 1);
    return 1;
}
void SDL_PauseAudioDevice(uint32_t, int pause)
{
    paused = pause != 0;
    if (!paused)
    {
        if (!starts) firstStartSamples = queuedSamples;
        ++starts;
    }
}
int SDL_QueueAudio(uint32_t, const void *, uint32_t len)
{
    queuedSamples += len / 2;
    totalSamples += len / 2;
    maxQueued = std::max(maxQueued, queuedSamples);
    return 0;
}
uint32_t SDL_GetQueuedAudioSize(uint32_t) { return queuedSamples * 2; }
void SDL_CloseAudioDevice(uint32_t) {}
}

int main(int argc, char **argv)
{
    if (argc != 2) { fprintf(stderr, "usage: audio-test ROM\n"); return 1; }
    AudioCallback(0, 0);
    AudioCallback(32767, 32767);
    Check("silence is zero PCM", g_audioBuf[0] == 0);
    Check("speaker amplitude is preserved", g_audioBuf[1] - g_audioBuf[0] == 32767);
    g_audioBuf.clear();
    for (int scenario = 0; scenario < 2; ++scenario)
    {
        stall = scenario != 0;
        clockMs = frames = queuedSamples = fraction = underruns = 0;
        totalSamples = starts = maxQueued = firstStartSamples = 0;
        paused = true;
        char romOption[] = "--rom", noBoot[] = "--no-autoboot";
        char *args[] = { argv[0], romOption, argv[1], noBoot };
        Check("player exits successfully", PlayerMain(4, args) == 0);
        CProcessor::Done();
        // 250 actual SystemFrame calls: assert against the samples the
        // real core generated, not just the frontend's timing constants.
        double generatedMs = totalSamples * 1000.0 / SAMPLERATE;
        printf("  %s: %.0f ms audio / %u ms clock, %u underruns, %u starts\n",
               stall ? "host stall" : "render jitter", generatedMs,
               clockMs, underruns, starts);
        Check("audio generation keeps up with wall time",
              fabs(generatedMs - clockMs + (stall ? 180 : 0)) <= 20);
        Check("playback starts with a buffer cushion",
              firstStartSamples >= 2 * SAMPLERATE / FRAMERATE);
        Check("no recurring underruns", underruns == (stall ? 1u : 0u));
        Check("host stall re-primes playback", starts == (stall ? 2u : 1u));
        Check("audio latency stays bounded", maxQueued <= 4 * SAMPLERATE / FRAMERATE);
    }
    return failures ? 1 : 0;
}
