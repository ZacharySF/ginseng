-- Expand manual onboarding from three screens to six guided steps.
-- Existing profiles retain their current step and remain valid.

alter table public.profiles
    drop constraint if exists profiles_onboarding_step_check;

alter table public.profiles
    add constraint profiles_onboarding_step_check
    check (onboarding_step between 1 and 6);

comment on column public.profiles.onboarding_step is
    'Guided setup progress: 1 welcome, 2 setup path, 3 cash, 4 income, 5 bills, 6 review.';
