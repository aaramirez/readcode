import { describe, expect, it } from 'vitest';
import { clampStep, stepNav, tourDocKey, tourIdOfDocKey, tourStepDocKey } from './tours';

describe('clampStep', () => {
  it('defaults to the first step', () => {
    expect(clampStep(6, undefined)).toBe(1);
  });
  it('keeps steps in range', () => {
    expect(clampStep(6, 3)).toBe(3);
    expect(clampStep(6, 6)).toBe(6);
  });
  it('clamps out-of-range steps', () => {
    expect(clampStep(6, 9)).toBe(6);
    expect(clampStep(6, 0)).toBe(1);
    expect(clampStep(6, -2)).toBe(1);
  });
  it('returns 0 for an empty tour', () => {
    expect(clampStep(0, 1)).toBe(0);
  });
});

describe('stepNav', () => {
  it('has no previous step at the start', () => {
    expect(stepNav(6, 1)).toEqual({ prev: null, next: 2 });
  });
  it('has no next step at the end', () => {
    expect(stepNav(6, 6)).toEqual({ prev: 5, next: null });
  });
  it('moves both ways in the middle', () => {
    expect(stepNav(6, 3)).toEqual({ prev: 2, next: 4 });
  });
  it('handles single-step and out-of-range tours', () => {
    expect(stepNav(1, 1)).toEqual({ prev: null, next: null });
    expect(stepNav(3, 10)).toEqual({ prev: 2, next: null });
    expect(stepNav(0, 1)).toEqual({ prev: null, next: null });
  });
});

describe('tour doc keys', () => {
  it('uses tours/<id>.json for the description and tours/<id>.json#<n> per step', () => {
    expect(tourDocKey('login')).toBe('tours/login.json');
    expect(tourStepDocKey('login', 1)).toBe('tours/login.json#1');
    expect(tourStepDocKey('login', 12)).toBe('tours/login.json#12');
  });

  it('extracts the tour id from either kind of key', () => {
    expect(tourIdOfDocKey('tours/login.json')).toBe('login');
    expect(tourIdOfDocKey('tours/login.json#3')).toBe('login');
    expect(tourIdOfDocKey('tours/a.b.json#10')).toBe('a.b');
    expect(tourIdOfDocKey('explain/tours/x.py.json')).toBeNull();
    expect(tourIdOfDocKey('tours/login.json#x')).toBeNull();
    expect(tourIdOfDocKey('overview.md')).toBeNull();
  });
});
