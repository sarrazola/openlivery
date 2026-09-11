// Inline bootstrap rendered as the first script in <body>, before any content
// paints. It resolves the stored preference the same way lib/theme.tsx does
// and stamps data-theme on <html>, so a reload never flashes the other theme.
// Plain ES5 in a string: it runs before the app bundle exists. Keep the
// storage key, cookie name and widget exclusion in step with lib/theme.tsx.
export const THEME_INIT_SCRIPT = `(function(){try{
if(location.pathname.indexOf('/widget/')===0)return;
var p=null;try{p=localStorage.getItem('openlivery.theme')}catch(e){}
if(p!=='system'&&p!=='light'&&p!=='dark'){var m=document.cookie.match(/(?:^|;\\s*)openlivery\\.theme=(system|light|dark)/);p=m?m[1]:'system'}
if(p==='system'){p=window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}
document.documentElement.setAttribute('data-theme',p);
}catch(e){}})();`;
