// src/utils/boxes.ts
import type { Box, BoxType } from '../types';

export const BOX_TYPES: BoxType[] = ['text', 'panel', 'face', 'body'];
export const BOX_RENDER_ORDER: BoxType[] = ['panel', 'face', 'body', 'text'];
export const EDITABLE_BOX_TYPES: BoxType[] = ['text', 'panel'];

export const normalizeBoxType = (value?: string | null): BoxType => {
  const key = String(value ?? 'text')
    .trim()
    .toLowerCase();
  if (key === 'textbox' || key === 'speech') {
    return 'text';
  }
  if (key === 'frame') {
    return 'panel';
  }
  if (key === 'face') {
    return 'face';
  }
  if (key === 'body') {
    return 'body';
  }
  if (key === 'panel' || key === 'text') {
    return key;
  }
  return 'text';
};

export const normalizeBox = (box: Box): Box => ({
  ...box,
  type: normalizeBoxType(box.type),
});
