#ifndef DISTRHO_PLUGIN_INFO_H_INCLUDED
#define DISTRHO_PLUGIN_INFO_H_INCLUDED

// Rename these together with the TTL (see docs/lv2-and-mod-rules.md).
#define DISTRHO_PLUGIN_BRAND       "New Horizon"
#define DISTRHO_PLUGIN_NAME        "Trance Atlantic"
#define DISTRHO_PLUGIN_URI         "https://github.com/Kiwooky/NHE-Trance-Atlantic"

#define DISTRHO_PLUGIN_HAS_UI       0
#define DISTRHO_PLUGIN_IS_RT_SAFE   1
#define DISTRHO_PLUGIN_NUM_INPUTS   1
#define DISTRHO_PLUGIN_NUM_OUTPUTS  2

// Control ports, in TTL order (indices start after the audio ports).
// The bypass port is always last.
enum Parameters {
    kSense = 0,
    kSong,
    kSwim,
    kDepth,
    kScatter,
    kThroat,
    kBlend,
    kTravel,
    kMode,
    kTails,
    kInputLevel,
    kBypass,
    kParameterCount
};

#endif
