function (event, funcs) {
    // Trance Atlantic face script. ES5 and small on purpose: if a face script
    // throws, mod-ui silently disables it.
    //  - Travel / Mode buttons step their setting; Travel lights pick directly.
    //  - Readouts: Song "#00".."#24" and Mode OFF / FIX / ENV, picked from pre-rendered strips.
    //  - Mode OFF darkens Throat, Sense, Song, Swim lights, the Travel lights,
    //    and the Song readout.
    //  - Orb: layer 1 always on; 2 = Depth, 3 = Scatter, 4 = Blend (0..100 -> 0..1);
    //    5 = the plugin's Input Level output (always on).
    // mod-ui doesn't echo a script's own set_port_value back, so we redraw after setting.
    var icon = event.icon;
    var d = event.data;
    var NEXT = { travel: { 0: 2, 2: 1, 1: 0 }, mode: { 0: 1, 1: 2, 2: 0 } };
    var ORB = { depth: '.ta-orb2', scatter: '.ta-orb3', blend: '.ta-orb4' };

    function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
    function draw() {
        var mode = Math.round(d.mode), travel = Math.round(d.travel), song = Math.round(d.song);
        var off = mode == 0;
        icon.find('.ta-sled').toggleClass('on', !off);
        icon.find('.ta-lens-mode .ta-text').css('background-position', (-43 * Math.max(0, Math.min(2, mode))) + 'px 0');
        icon.find('.ta-lens-song .ta-text').css('background-position', (-43 * Math.max(0, Math.min(24, song))) + 'px 0');
        icon.find('.ta-lens-song').toggleClass('dim', off);
        icon.find('.ta-tled').each(function () {
            var el = jQuery(this);
            el.toggleClass('on', !off && parseInt(el.attr('data-value'), 10) == travel);
        });
    }
    function orb(sym, v) {
        if (ORB[sym]) icon.find(ORB[sym]).css('opacity', clamp01(v / 100));
        if (sym == 'input_level') icon.find('.ta-orb5').css('opacity', clamp01(parseFloat(v)));
    }
    function set(sym, v) {
        d[sym] = v;
        funcs.set_port_value(sym, v);
        draw();
    }
    // act on press; ignore the emulated mouse events that follow a touch
    function onPress(el, fn) {
        el.on('touchstart', function (e) {
            e.preventDefault(); e.stopPropagation();
            d.lastTouch = new Date().getTime();
            fn(jQuery(this), e);
        });
        el.on('mousedown', function (e) {
            e.preventDefault(); e.stopPropagation();
            if (d.lastTouch && new Date().getTime() - d.lastTouch < 1000) return;
            fn(jQuery(this), e);
        });
        el.on('click', function (e) { e.preventDefault(); e.stopPropagation(); });
    }

    if (event.type == 'start') {
        d.travel = 2; d.mode = 2; d.song = 5;
        var ports = event.ports || [];
        for (var i = 0; i < ports.length; i++) {
            var p = ports[i];
            d[p.symbol] = p.value;
            orb(p.symbol, p.value);
        }
        draw();
        onPress(icon.find('[ta-step]'), function (el) {
            var sym = el.attr('ta-step');
            el.addClass('down');
            set(sym, NEXT[sym][Math.round(d[sym])]);
        });
        icon.find('[ta-step]').on('mouseup mouseleave touchend touchcancel', function () {
            jQuery(this).removeClass('down');
        });
        onPress(icon.find('[ta-pick]'), function (el) {
            set(el.attr('ta-pick'), parseInt(el.attr('data-value'), 10));
        });
    } else if (event.type == 'change') {
        d[event.symbol] = event.value;
        orb(event.symbol, event.value);
        if (event.symbol == 'mode' || event.symbol == 'travel' || event.symbol == 'song') draw();
    }
}
