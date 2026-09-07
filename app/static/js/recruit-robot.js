(() => {
  'use strict';
  const robot=document.querySelector('[data-recruit-robot]');
  if(!robot)return;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let timer;
  const greet=()=>{
    if(reduced.matches||robot.classList.contains('is-playing'))return;
    robot.classList.add('is-playing');
    clearTimeout(timer);timer=setTimeout(()=>robot.classList.remove('is-playing'),1800);
  };
  robot.addEventListener('click',greet);
  if('IntersectionObserver' in window){
    const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){greet();observer.disconnect();}},{threshold:.6});
    observer.observe(robot);
  }
  reduced.addEventListener?.('change',()=>{if(reduced.matches)robot.classList.remove('is-playing');});
})();
