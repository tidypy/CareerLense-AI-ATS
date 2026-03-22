import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const CareerLensApp());

    // Verify that our app name is present
    expect(find.text('CareerLens AI'), findsWidgets);
  });
}
