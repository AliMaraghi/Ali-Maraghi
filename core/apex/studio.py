"""Reproducible editing package for a proposed timeline; never a rendered film."""
from html import escape


def edit_package(manifest):
    timeline = manifest.get('timeline')
    if not isinstance(timeline,list) or not 1 <= len(timeline) <= 100:
        raise ValueError('Bounded timeline required')
    elapsed, ids, captions, script = 0, set(), [], []
    def stamp(seconds):
        return f'{seconds//3600:02}:{seconds%3600//60:02}:{seconds%60:02},000'
    for shot in timeline:
        for key in ('start_seconds','end_seconds'):
            if type(shot.get(key)) is not int:
                raise ValueError('Integer timeline required')
        if shot['start_seconds'] != elapsed or not elapsed < shot['end_seconds'] <= 90:
            raise ValueError('Timeline must be continuous, positive and at most 90 seconds')
        if not isinstance(shot.get('shot_id'),str) or shot['shot_id'] in ids:
            raise ValueError('Unique shot IDs required')
        ids.add(shot['shot_id'])
        narration = shot.get('narration')
        if not isinstance(narration,str) or len(narration)>4000 or any(ord(c)<32 for c in narration):
            raise ValueError('Narration must be one bounded plain-text line')
        if narration.strip():
            captions.append(f'{len(captions)+1}\n{stamp(elapsed)} --> {stamp(shot["end_seconds"])}\n{escape(narration)}\n')
        script.append({'shot_id':shot['shot_id'],'start_seconds':elapsed,'end_seconds':shot['end_seconds'],'narration':narration})
        elapsed = shot['end_seconds']
    if not 60 <= elapsed <= 90 or manifest.get('duration_seconds') != elapsed:
        raise ValueError('Duration must match the 60-90 second timeline')
    return {'script':script,'subtitles_srt':'\n'.join(captions),'duration_seconds':elapsed,
            'status':'PREPRODUCTION_ONLY','film_completed':False,
            'qc':{'timeline':'PASS_STRUCTURE_ONLY','media_decode':'NOT_TESTED',
                  'audio_loudness':'NOT_TESTED','caption_speech_sync':'NOT_TESTED',
                  'rights':'REQUIRES_INDEPENDENT_REVIEW'},
            'limitation':'Caption timing follows planned shots, not measured speech. No media was opened or rendered.'}
