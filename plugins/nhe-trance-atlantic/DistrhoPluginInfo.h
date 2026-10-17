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
    // Envelope
    kSense = 0,
    kSwim,
    kThroat,
    kMode,
    // Pitch
    kSong,
    kTravel,
    // Reverb
    kDepth,
    kScatter,
    // Mix
    kBlend,
    kTails,
    kInputLevel,
    kBypass,
    kParameterCount
};

// Port groups, in the order MOD lists them (the TTL gives each its lv2:index).
enum PortGroups {
    kGroupEnvelope = 0,
    kGroupPitch,
    kGroupReverb,
    kGroupMix,
    kGroupCount
};

#endif
